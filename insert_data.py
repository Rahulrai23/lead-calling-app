import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

# Insert user
cursor.execute("INSERT INTO users (username, role) VALUES (?, ?)", 
               ("caller1", "caller"))

# Insert lead
cursor.execute("""
INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
VALUES (?, ?, ?, ?, ?)
""", ("Rahul Sharma", "9876543210", "caller1", "pending", ""))

conn.commit()
conn.close()

print("Sample data inserted")
