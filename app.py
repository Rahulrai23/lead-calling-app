# =========================================================
# LEAD CALLING APP – MANAGER → CALLER (STABLE VERSION)
# =========================================================

import os
import psycopg2
import pandas as pd
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# APP CONFIG
# =========================================================

app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"

# =========================================================
# DATABASE HELPERS
# =========================================================

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

# =========================================================
# AUTH ROUTES
# =========================================================

@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = query_db(
            "SELECT username, password, role FROM users WHERE username=%s",
            (username,)
        )

        if not user or not check_password_hash(user[0][1], password):
            return render_template("login.html", error="Invalid credentials")

        session["username"] = user[0][0]
        session["role"] = user[0][2]

        if user[0][2] == "manager":
            return redirect("/manager")
        else:
            return redirect(f"/caller/{username}")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================================================
# INITIAL MANAGER (ONE-TIME)
# =========================================================

@app.route("/create_admin")
def create_admin():
    password = generate_password_hash("admin123")

    query_db("DELETE FROM users WHERE username='admin'", fetch=False)

    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'manager')
    """, ("admin", password), fetch=False)

    return "Admin RESET → admin / admin123"


# =========================================================
# MANAGER ROUTES
# =========================================================

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone, assigned_to, call_status, remarks
        FROM leads
        ORDER BY id DESC
    """)

    callers = query_db("""
        SELECT username FROM users WHERE role='caller'
    """)

    return render_template(
        "manager.html",
        leads=leads,
        callers=callers
    )


@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/login")

    username = request.form["username"].strip()
    password = request.form["password"].strip()

    if not username or not password:
        return "Username and password required"

    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'caller')
        ON CONFLICT (username) DO NOTHING
    """, (username, generate_password_hash(password)), fetch=False)

    return redirect("/manager")


@app.route("/upload_csv", methods=["POST"])
def upload_csv():
    if session.get("role") != "manager":
        return redirect("/login")

    file = request.files.get("file")
    if not file or file.filename == "":
        return "No file selected"

    df = pd.read_csv(file)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    required = {"name", "phone", "assigned_to"}
    if not required.issubset(df.columns):
        return f"CSV must contain columns {required}"

    valid_callers = [
        c[0].lower() for c in query_db(
            "SELECT username FROM users WHERE role='caller'"
        )
    ]

    for _, row in df.iterrows():
        if row["assigned_to"].strip().lower() not in valid_callers:
            continue

        query_db("""
            INSERT INTO leads (name, phone, assigned_to, call_status, remarks)
            VALUES (%s, %s, %s, 'pending', '')
        """, (
            row["name"].strip(),
            str(row["phone"]).strip(),
            row["assigned_to"].strip()
        ), fetch=False)

    return redirect("/manager")


# =========================================================
# CALLER ROUTES
# =========================================================

@app.route("/caller")
def caller_home():
    if session.get("role") != "caller":
        return redirect("/login")

    callers = query_db("""
        SELECT DISTINCT assigned_to
        FROM leads
        ORDER BY assigned_to
    """)

    return render_template("caller_home.html", callers=callers)


@app.route("/caller/<caller_name>")
def caller_page(caller_name):
    if session.get("role") != "caller" or session.get("username") != caller_name:
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone
        FROM leads
        WHERE assigned_to=%s AND call_status='pending'
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
        WHERE id=%s
    """, (lead_id,), fetch=False)

    return {"status": "ok"}


@app.route("/submit", methods=["POST"])
def submit():
    lead_id = request.form["lead_id"]
    remarks = request.form["remarks"]
    caller_name = request.form["caller_name"]

    query_db("""
        UPDATE leads
        SET remarks=%s, call_status='completed'
        WHERE id=%s
    """, (remarks, lead_id), fetch=False)

    return redirect(f"/caller/{caller_name}")


# =========================================================
# START APP
# =========================================================

if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print("INIT DB ERROR:", e)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
