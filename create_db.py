import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    role TEXT
)
""")

# Leads table
cursor.execute("""
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    assigned_to TEXT,
    call_status TEXT,
    remarks TEXT
)
""")

conn.commit()
conn.close()

print("Database created successfully")
