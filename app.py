import psycopg2
import os
from datetime import datetime
import pandas as pd
from flask import Flask, render_template, request, redirect, session

app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"
app.config["DEBUG"] = True


# ---------- DATABASE HELPERS ----------

def get_db():
    return psycopg2.connect(os.environ.get("DATABASE_URL"))


def query_db(query, params=None, fetch=True):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, params or ())
    result = cur.fetchall() if fetch else None
    if not fetch:
        conn.commit()
    cur.close()
    conn.close()
    return result


def init_db():
    query_db("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
    """, fetch=False)

    query_db("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            assigned_to TEXT,
            call_status TEXT,
            remarks TEXT,
            call_attempt_time TIMESTAMP
        )
    """, fetch=False)


# ---------- AUTH ROUTES ----------

@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = query_db("""
            SELECT username, role
            FROM users
            WHERE username = %s AND password = %s
        """, (username, password))

        if not user:
            return render_template("login.html", error="Invalid credentials")

        session["username"] = user[0][0]
        session["role"] = user[0][1]

        if user[0][1] == "manager":
            return redirect("/manager")
        else:
            return redirect(f"/caller/{username}")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/create_admin")
def create_admin():
    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, %s)
        ON CONFLICT (username) DO NOTHING
    """, ("admin", "admin123", "manager"), fetch=False)

    return "Admin created"


# ---------- MANAGER ROUTES ----------

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone, assigned_to, call_status, remarks
        FROM leads
        ORDER BY id DESC
    """)
    return render_template("manager.html", leads=leads)


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    file = request.files.get("file")
    if not file or file.filename == "":
        return "No file selected"

    df = pd.read_csv(file)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    required = {"name", "phone", "assigned_to"}
    if not required.issubset(df.columns):
        return f"CSV must contain columns {required}"

    for _, row in df.iterrows():
        query_db("""
            INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
            VALUES (%s, %s, %s, 'pending', '')
        """, (
            row["name"].strip(),
            str(row["phone"]).strip(),
            row["assigned_to"].strip()
        ), fetch=False)

    return redirect("/manager")


@app.route("/add_lead", methods=["POST"])
def add_lead():
    query_db("""
        INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
        VALUES (%s, %s, %s, 'pending', '')
    """, (
        request.form["name"],
        request.form["phone"],
        request.form["assigned_to"]
    ), fetch=False)

    return redirect("/manager")


@app.route("/report")
def report():
    if session.get("role") != "manager":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone, assigned_to, call_status, remarks
        FROM leads
        ORDER BY id DESC
    """)
    return render_template("report.html", leads=leads)


# ---------- CALLER ROUTES ----------

@app.route("/caller")
def caller_home():
    if session.get("role") != "caller":
        return redirect("/login")

    callers = query_db("""
        SELECT DISTINCT assigned_to
        FROM leads
        WHERE assigned_to IS NOT NULL
          AND assigned_to != ''
        ORDER BY assigned_to
    """)
    return render_template("caller_home.html", callers=callers)


@app.route("/caller/<caller_name>", endpoint="caller")
def caller_page(caller_name):
    if session.get("role") != "caller" or session.get("username") != caller_name:
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone
        FROM leads
        WHERE LOWER(TRIM(assigned_to)) = LOWER(TRIM(%s))
          AND call_status = 'pending'
    """, (caller_name,))

    return render_template(
        "caller.html",
        leads=leads,
        caller_name=caller_name
    )


@app.route("/mark_called/<int:lead_id>", methods=["POST"])
def mark_called(lead_id):
    query_db("""
        UPDATE leads
        SET call_attempt_time = NOW()
        WHERE id = %s
    """, (lead_id,), fetch=False)
    return {"status": "ok"}


@app.route("/submit", methods=["POST"])
def submit():
    lead_id = request.form["lead_id"]
    remarks = request.form["remarks"]
    caller_name = request.form["caller_name"]

    call_time = query_db("""
        SELECT call_attempt_time FROM leads WHERE id = %s
    """, (lead_id,))

    if not call_time or not call_time[0][0]:
        return "Please call before submitting remarks."

    query_db("""
        UPDATE leads
        SET remarks = %s, call_status = 'completed'
        WHERE id = %s
    """, (remarks, lead_id), fetch=False)

    return redirect(f"/caller/{caller_name}")


@app.route("/fix_callers")
def fix_callers():
    query_db("""
        UPDATE leads
        SET assigned_to = TRIM(assigned_to)
        WHERE assigned_to IS NOT NULL
    """, fetch=False)
    return "Caller names cleaned"


# ---------- START APP ----------

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
