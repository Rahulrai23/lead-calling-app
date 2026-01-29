# =========================================================
# LEAD CALLING APP – ADMIN → MANAGER → CALLER (FINAL WORKING)
# =========================================================

import os
import psycopg2
import pandas as pd
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"

# ================= DATABASE =================

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
        CREATE TABLE IF NOT EXISTS states (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """, fetch=False)

    query_db("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            state_id INTEGER REFERENCES states(id)
        )
    """, fetch=False)

    query_db("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            assigned_to TEXT,
            call_status TEXT DEFAULT 'pending'
        )
    """, fetch=False)

# ================= AUTH =================

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"]

        user = query_db(
            "SELECT id, password, role FROM users WHERE username=%s",
            (u,)
        )

        if not user or not check_password_hash(user[0][1], p):
            return render_template("login.html", error="Invalid credentials")

        session.clear()
        session["user_id"] = user[0][0]
        session["username"] = u
        session["role"] = user[0][2]

        if user[0][2] == "admin":
            return redirect("/admin")
        elif user[0][2] == "manager":
            return redirect("/manager")
        else:
            return redirect(f"/caller/{u}")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/whoami")
def whoami():
    return jsonify({
        "username": session.get("username"),
        "role": session.get("role")
    })

# ================= ADMIN =================

@app.route("/create_admin")
def create_admin():
    query_db("DELETE FROM users WHERE username='admin'", fetch=False)
    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'admin')
    """, ("admin", generate_password_hash("admin123")), fetch=False)
    return "Admin created → admin / admin123"

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if session.get("role") != "admin":
        return redirect("/login")

    if request.method == "POST":
        state = request.form["state"].strip()
        query_db(
            "INSERT INTO states (name) VALUES (%s) ON CONFLICT DO NOTHING",
            (state,),
            fetch=False
        )

    states = query_db("SELECT id, name FROM states")
    managers = query_db("""
        SELECT u.username, s.name
        FROM users u
        JOIN states s ON u.state_id = s.id
        WHERE u.role='manager'
    """)

    return render_template(
        "admin.html",
        states=states,
        managers=managers
    )

@app.route("/create_manager", methods=["POST"])
def create_manager():
    if session.get("role") != "admin":
        return redirect("/login")

    query_db("""
        INSERT INTO users (username, password, role, state_id)
        VALUES (%s, %s, 'manager', %s)
        ON CONFLICT (username) DO NOTHING
    """, (
        request.form["username"],
        generate_password_hash(request.form["password"]),
        request.form["state_id"]
    ), fetch=False)

    return redirect("/admin")

# ================= MANAGER =================

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    callers = query_db("""
        SELECT username FROM users
        WHERE role='caller'
        AND state_id = (SELECT state_id FROM users WHERE id=%s)
    """, (session["user_id"],))

    leads = query_db("""
        SELECT name, phone, assigned_to, call_status
        FROM leads
    """)

    stats = query_db("""
        SELECT
            COUNT(*) FILTER (WHERE call_status='pending'),
            COUNT(*) FILTER (WHERE call_status='completed')
        FROM leads
    """)

    return render_template(
        "manager.html",
        callers=callers,
        leads=leads,
        stats=stats[0]
    )

@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/login")

    query_db("""
        INSERT INTO users (username, password, role, state_id)
        VALUES (%s, %s, 'caller',
            (SELECT state_id FROM users WHERE id=%s)
        )
    """, (
        request.form["username"],
        generate_password_hash(request.form["password"]),
        session["user_id"]
    ), fetch=False)

    return redirect("/manager")

@app.route("/upload_leads", methods=["POST"])
def upload_leads():
    if session.get("role") != "manager":
        return redirect("/login")

    file = request.files.get("file")
    if not file or file.filename == "":
        return "No file selected"

    try:
       if filename.endswith(".csv"):
    df = pd.read_csv(file)

elif filename.endswith(".xlsx"):
    df = pd.read_excel(file, engine="openpyxl")

else:
    return "Only CSV or XLSX files allowed"

    except Exception as e:
        return f"File read error: {e}"

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    if not {"name", "phone", "assigned_to"}.issubset(df.columns):
        return "Required columns: name, phone, assigned_to"

    valid_callers = [
        r[0] for r in query_db("""
            SELECT username FROM users
            WHERE role='caller'
            AND state_id=(SELECT state_id FROM users WHERE id=%s)
        """, (session["user_id"],))
    ]

    inserted = 0
    for _, row in df.iterrows():
        if row["assigned_to"] not in valid_callers:
            continue

        query_db("""
            INSERT INTO leads (name, phone, assigned_to)
            VALUES (%s, %s, %s)
        """, (
            str(row["name"]).strip(),
            str(row["phone"]).strip(),
            str(row["assigned_to"]).strip()
        ), fetch=False)

        inserted += 1

    return f"✅ {inserted} leads uploaded successfully"

# ================= CALLER =================

@app.route("/caller/<caller_name>")
def caller(caller_name):
    if session.get("role") != "caller":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone
        FROM leads
        WHERE assigned_to=%s AND call_status='pending'
    """, (caller_name,))

    return render_template("caller.html", leads=leads, caller_name=caller_name)

# ================= START =================

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
