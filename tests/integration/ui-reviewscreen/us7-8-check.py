#!/usr/bin/env python3
"""Exercise actual US7 adapter against US8 using a disposable SQLite database."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# NOTE Since no aggreed apon name for survey_id, bundleNum_SurveyNum was used temporarily
# Reads optional frontend, backend, fixture, and report locations.
parser = argparse.ArgumentParser(description=__doc__)
root = Path(__file__).resolve().parents[3]
parser.add_argument('--frontend', type=Path, default=root / 'frontend')
parser.add_argument('--backend', type=Path, default=root / 'backend')
parser.add_argument('--seed', type=Path, help='Standalone SQL seed containing schema and records')
parser.add_argument('--survey', default='216417_1', help='Survey ID in the SQL seed')
parser.add_argument('--report', type=Path, help='Optional output report path')
args = parser.parse_args()
args.frontend = args.frontend.resolve()
args.backend = args.backend.resolve()
seed = args.seed.resolve() if args.seed else args.backend / 'seed_demo.sql'
report_path = args.report.resolve() if args.report else Path(__file__).resolve().parent / 'report.json'
if not seed.exists() or not (args.backend / 'main.py').exists():
    parser.error('SQL seed or backend/main.py was not found. Supply --seed and --backend.')
try:
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
except ImportError:
    sys.exit('Install dependencies first: python -m pip install fastapi sqlalchemy httpx')

# Expected values are read directly from the seeded database, never from
# survey.json or an API response. JSON below is only an inter-process format.
script_dir = Path(__file__).resolve().parent
results = []

# Creates a disposable directory and SQLite database for this run.
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

    # The standalone seed defines its own schema; do not run create.sql too.
    connection = engine.raw_connection()
    try:
        connection.executescript(seed.read_text())
        cursor = connection.cursor()
        if not cursor.execute('SELECT 1 FROM surveys WHERE survey_id=?', (args.survey,)).fetchone():
            raise RuntimeError(f'Survey {args.survey} is missing from {seed}')
        person = cursor.execute('SELECT reviewer_id,name FROM reviewers ORDER BY reviewer_id LIMIT 1').fetchone()
        if person is None:
            raise RuntimeError('SQL seed must contain a reviewer.')
        fixture = {'id': args.survey, 'pages': [], 'reviewer': {'id': person[0], 'name': person[1]}}
        rows = cursor.execute('SELECT page_id,category,import_path FROM pages WHERE survey_id=? ORDER BY page_id', (args.survey,)).fetchall()
        for page_id, category, image_url in rows:
            fields = []
            for title, value in cursor.execute('SELECT field_title,text_raw FROM fields WHERE page_id=? ORDER BY field_title', (page_id,)).fetchall():
                fields.append({'id': title, 'value': value})
            for number, title, value in cursor.execute('SELECT resident_no,resident_field_title,text_raw FROM resident_fields WHERE page_id=? ORDER BY resident_no,resident_field_title', (page_id,)).fetchall():
                fields.append({'id': f'residents.{number}.{title}', 'value': value})
            for number, residence, value in cursor.execute('SELECT child_no,residence,text_raw FROM other_children WHERE page_id=? ORDER BY child_no', (page_id,)).fetchall():
                fields.append({'id': f'other_children.{residence}.{number}', 'value': value})
            for number, value in cursor.execute('SELECT annotation_no,text_raw FROM annotations WHERE page_id=? ORDER BY annotation_no', (page_id,)).fetchall():
                fields.append({'id': f'annotation.{number}', 'value': value})
            fixture['pages'].append({'id': page_id, 'type': category, 'imageUrl': image_url, 'fields': fields})
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

# Prints each adapter/backend check result.
for result in results:
    print(f'{result["status"]}: {result["name"]}')
    if result.get('reason'): print('  '+result['reason'])
# Writes the report and returns a nonzero exit code if any check failed,
# allowing npm test:all to detect the integration failure.
passed = sum(r['status']=='PASS' for r in results)
print(f'\n{passed}/{len(results)} checks passed. Production database was not used.')
report = {'results':results,'seed':str(seed),'scope':'Actual frontend api.ts/model.ts through FastAPI TestClient; no browser, Vite proxy, images or live deployment.'}
report_path.write_text(json.dumps(report,indent=2))
sys.exit(0 if passed == len(results) else 1)