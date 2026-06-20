import sqlite3
from pathlib import Path

db_path = Path('data/db/jav_database.db')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== actresses table columns ===')
cur.execute("PRAGMA table_info(actresses);")
for row in cur.fetchall():
    print(row)

print('\n=== Existing tables ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
for row in cur.fetchall():
    print(row[0])

print('\n=== user_version ===')
cur.execute('PRAGMA user_version')
print(cur.fetchone()[0])

print('\n=== actress_images / actress_aliases exist? ===')
for tbl in ('actress_images', 'actress_aliases'):
    try:
        cur.execute(f"SELECT COUNT(*) FROM {tbl} LIMIT 1")
        print(f'{tbl}: exists (0+ rows)')
    except sqlite3.OperationalError as e:
        print(f'{tbl}: does not exist ({e})')

conn.close()
print('\nSchema check complete.')