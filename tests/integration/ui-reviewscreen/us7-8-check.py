#!/usr/bin/env python3
"""Exercise actual US7 adapter against US8 using a disposable SQLite database."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

parser = argparse.ArgumentParser(description=__doc__)
root = Path(__file__).resolve().parents[3]
parser.add_argument('--frontend', type=Path, default=root / 'frontend')
parser.add_argument('--backend', type=Path, default=root / 'backend')
parser.add_argument('--demo', type=Path, help='Optional normalized demo JSON')
parser.add_argument('--report', type=Path, help='Optional output report path')
args = parser.parse_args()
args.frontend = args.frontend.resolve()
args.backend = args.backend.resolve()
demo = args.demo.resolve() if args.demo else args.frontend / 'public/us7-demo/survey.json'
if not demo.exists() or not (args.backend / 'main.py').exists():
    parser.error('Frontend demo or backend/main.py was not found. Supply --frontend and --backend.')
try:
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
except ImportError:
    sys.exit('Install dependencies first: python -m pip install fastapi sqlalchemy httpx')

fixture = json.loads(demo.read_text())
script_dir = Path(__file__).resolve().parent
results = []
notes = []
with tempfile.TemporaryDirectory(prefix='us7-us8-check-') as temporary:
    # Relative backend DB paths can only point inside this disposable directory.
    old_cwd = Path.cwd()
    os.chdir(temporary)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.backend.parent))
    from backend import database
    engine = create_engine(f'sqlite:///{Path(temporary) / "test.sqlite"}', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    database.engine = engine
    database.SessionLocal = sessionmaker(bind=engine)
    from backend.main import app, get_db

    # Use the actual SQL schema, including its constraints, not simplified ORM tables.
    connection = engine.raw_connection()
    try:
        connection.executescript((args.backend / 'create.sql').read_text())
        cursor = connection.cursor()
        cursor.execute('INSERT INTO bundles(bundle_id,source_pdf) VALUES (?,?)', ('integration-demo', 'synthetic-demo.pdf'))
        cursor.execute('INSERT INTO surveys(survey_id,bundle_id) VALUES (?,?)', (fixture['id'], 'integration-demo'))
        for category in {p['type'] for p in fixture['pages']}:
            cursor.execute('INSERT INTO categories(category) VALUES (?)', (category,))
        cursor.execute('INSERT INTO reviewers(reviewer_id,name) VALUES (?,?)', (900001, 'Seeded integration reviewer'))
        for page in fixture['pages']:
            cursor.execute('INSERT INTO pages(page_id,import_path,survey_id,bundle_id,category,revision_no) VALUES (?,?,?,?,?,0)', (page['id'],page['imageUrl'],fixture['id'],'integration-demo',page['type']))
            residents = set()
            child_number = 0
            for field in page['fields']:
                fid, value = field['id'], field['value']
                parts = fid.split('.')
                if parts[0] == 'residents':
                    number = int(parts[1])
                    if number not in residents:
                        cursor.execute('INSERT INTO residents(page_id,resident_no) VALUES (?,?)', (page['id'],number))
                        residents.add(number)
                    cursor.execute('INSERT INTO resident_fields(page_id,resident_no,resident_field_title,text_raw) VALUES (?,?,?,?)', (page['id'],number,'.'.join(parts[2:]),value))
                elif parts[0] == 'other_children':
                    # Demo numbers restart within residence; SQL child_no is unique per page.
                    # Assign unique fixture IDs and explicitly report the incompatibility.
                    number = child_number
                    child_number += 1
                    if number != int(parts[2]):
                        notes.append(f'Demo {fid}: SQL requires a page-wide child number; fixture uses {number}. This is a real identity mismatch, not a passing mapping.')
                    cursor.execute('INSERT INTO other_children(page_id,child_no,residence,text_raw) VALUES (?,?,?,?)', (page['id'],number,parts[1],value))
                elif parts[0] in ('annotation','annotations'):
                    cursor.execute('INSERT INTO annotations(page_id,annotation_no,text_raw) VALUES (?,?,?)', (page['id'],int(parts[1]),value))
                else:
                    cursor.execute('INSERT INTO fields(page_id,field_title,text_raw) VALUES (?,?,?)', (page['id'],fid,value))
        connection.commit()
    finally:
        connection.close()
    def test_db():
        with database.SessionLocal() as session:
            yield session
    app.dependency_overrides[get_db] = test_db
    fixture_path = Path(temporary) / 'fixture.json'
    fixture_path.write_text(json.dumps(fixture))
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            process = subprocess.Popen(['node',str(script_dir/'us7-8-check.mjs'),str(args.frontend),str(fixture_path)], stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                for line in process.stdout:
                    message = json.loads(line)
                    if message['type'] == 'done':
                        results = message['results']
                        break
                    url = message['url']
                    if not url.startswith('/api/'):
                        raise RuntimeError(f'Unexpected fetch URL: {url}; runner supports current /api adapter only.')
                    route = url[len('/api'):]
                    response = client.request(message['method'],route,content=message.get('body'),headers={'Content-Type':'application/json'})
                    process.stdin.write(json.dumps({'id':message['id'],'status':response.status_code,'body':response.text})+'\n')
                    process.stdin.flush()
                code = process.wait(timeout=15)
                if code or not results:
                    raise RuntimeError(f'Frontend runner did not finish successfully (exit {code}).')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    finally:
        app.dependency_overrides.pop(get_db,None)
        engine.dispose()
        os.chdir(old_cwd)

for result in results:
    print(f'{result["status"]}: {result["name"]}')
    if result.get('reason'): print('  '+result['reason'])
for note in notes: print('FIXTURE NOTE: '+note)
passed = sum(r['status']=='PASS' for r in results)
print(f'\n{passed}/{len(results)} checks passed. Production database was not used.')
report = {'results':results,'fixture_notes':notes,'scope':'Actual frontend api.ts/model.ts through FastAPI TestClient; no browser, Vite proxy, images or live deployment.'}
(args.report.resolve() if args.report else script_dir/'report.json').write_text(json.dumps(report,indent=2))
sys.exit(0 if passed == len(results) else 1)
