import psycopg2
import os

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    name TEXT,
    phone TEXT,
    assigned_to TEXT,
    call_status TEXT,
    remarks TEXT,
    call_attempt_time TIMESTAMP
)
""")

conn.commit()
cur.close()
conn.close()

print("PostgreSQL tables created")
