"""Create the separate demo database; never overwrite an existing file."""
from pathlib import Path
import sqlite3

def main():
    folder = Path(__file__).resolve().parent
    target = folder / 'us7-demo.sqlite'
    with target.open('xb'):
        pass
    connection = sqlite3.connect(target)
    try:
        connection.executescript((folder / 'seed_demo.sql').read_text())
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Seed contains invalid references.')
        print(f'Created {target}; open US7 with ?survey=216417_1')
    finally:
        connection.close()

if __name__ == '__main__':
    main()
