import psycopg2
import os
from datetime import datetime, timedelta
import pandas as pd

from flask import Flask, render_template, request, redirect

app = Flask(__name__)
def init_db():
    conn = get_db()
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

def get_db():
    database_url = os.environ.get("DATABASE_URL")
    conn = psycopg2.connect(database_url)
    return conn

@app.route("/")
def login():
    return render_template("login.html")
@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    try:
        import pandas as pd
        import os

        file = request.files.get("file")

        if not file or file.filename == "":
            return "ERROR: No file selected"

        if not os.path.exists("uploads"):
            os.makedirs("uploads")

        filepath = os.path.join("uploads", file.filename)
        file.save(filepath)

        # Read CSV
        df = pd.read_csv(filepath)

        # 🔧 NORMALIZE COLUMN NAMES (CRITICAL FIX)
        df.columns = (
            df.columns
            .str.strip()        # remove spaces
            .str.lower()        # lowercase
            .str.replace(" ", "_")  # replace spaces with _
        )

        # Expected columns
        required_columns = {"name", "phone", "assigned_to"}

        if not required_columns.issubset(df.columns):
            return (
                f"ERROR: CSV must contain columns: {required_columns}. "
                f"Found columns: {list(df.columns)}"
            )

        db = get_db()

        for _, row in df.iterrows():
            db.execute("""
                INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
                VALUES (%s, %s, %s, 'pending', '')
            """, (
                str(row["name"]),
                str(row["phone"]),
                str(row["assigned_to"])
            ))

        db.commit()

        return "CSV uploaded successfully. <a href='/manager'>Go back</a>"

    except Exception as e:
        return f"CSV UPLOAD ERROR: {str(e)}"

@app.route("/manager")
def manager():
    db = get_db()
    leads = db.execute("""
        SELECT id, name, phone, assigned_to, call_status, remarks
        FROM leads
        ORDER BY id DESC
    """).fetchall()
    return render_template("manager.html", leads=leads)

@app.route("/report")
def report():
    db = get_db()
    leads = db.execute("""
        SELECT id, name, phone, assigned_to, call_status, remarks
        FROM leads
        ORDER BY id DESC
    """).fetchall()
    return render_template("report.html", leads=leads)

@app.route("/add_lead", methods=["POST"])
def add_lead():
    name = request.form["name"]
    phone = request.form["phone"]
    assigned_to = request.form["assigned_to"]

    db = get_db()
    db.execute("""
        INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
        VALUES (?, ?, ?, 'pending', '')
    """, (name, phone, assigned_to))
    db.commit()

    return redirect("/manager")

@app.route("/caller")
def caller():
    db = get_db()
    leads = db.execute("""
        SELECT * FROM leads
        WHERE assigned_to='Anay Sarkar'
        AND call_status='pending'
    """).fetchall()
    return render_template("caller.html", leads=leads)

@app.route("/submit", methods=["POST"])
def submit():
    lead_id = request.form["lead_id"]
    remarks = request.form["remarks"]

    if remarks.strip() == "":
        return "Remarks required"

    db = get_db()
    db.execute("""
        UPDATE leads 
        SET remarks=?, call_status='completed'
        WHERE id=%s
    """, (remarks, lead_id))
    db.commit()

    return redirect("/caller")

import os

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



