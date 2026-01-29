# =========================================================
# LEAD CALLING APP – MANAGER → CALLER (FINAL STABLE)
# =========================================================

import os
import psycopg2
import pandas as pd
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super-secret-key-change-this"

# ---------------- DB HELPERS ----------------

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

# ---------------- INIT DB ----------------

def init_db():
    query_db("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """, fetch=False)

    query_db("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            assigned_to TEXT,
            call_status TEXT DEFAULT 'pending',
            remarks TEXT,
            call_start_time TIMESTAMP,
            call_end_time TIMESTAMP,
            call_duration INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            reassigned_count INTEGER DEFAULT 0
        )
    """, fetch=False)

# ---------------- DIAGNOSTIC ----------------

@app.route("/whoami")
def whoami():
    return jsonify({
        "username": session.get("username"),
        "role": session.get("role")
    })

# ---------------- AUTH ----------------

@app.route("/")
def home():
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = query_db(
            "SELECT username, password, role FROM users WHERE username=%s",
            (username,)
        )

        if not user or not check_password_hash(user[0][1], password):
            return render_template("login.html", error="Invalid credentials")

        session.clear()
        session["username"] = user[0][0]
        session["role"] = user[0][2]

        if user[0][2] == "manager":
            return redirect("/manager")

        return redirect(f"/caller/{username}")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- ADMIN SEED ----------------

@app.route("/create_admin")
def create_admin():
    query_db("DELETE FROM users WHERE username='admin'", fetch=False)
    query_db(
        "INSERT INTO users (username, password, role) VALUES (%s,%s,'manager')",
        ("admin", generate_password_hash("admin123")),
        fetch=False
    )
    return "Admin created → admin / admin123"

@app.route("/hard_reset_db")
def hard_reset_db():
    query_db("DROP TABLE IF EXISTS leads CASCADE", fetch=False)
    query_db("DROP TABLE IF EXISTS users CASCADE", fetch=False)
    init_db()
    return "DATABASE RESET COMPLETED"

# ---------------- MANAGER ----------------

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone, assigned_to, call_status, remarks, call_duration, reassigned_count
        FROM leads
        ORDER BY id DESC
    """)

    callers = query_db("SELECT username FROM users WHERE role='caller'")

    stats = query_db("""
        SELECT
            SUM(CASE WHEN call_status='pending' THEN 1 ELSE 0 END),
            SUM(CASE WHEN call_status='completed' THEN 1 ELSE 0 END)
        FROM leads
    """)

    stats = stats[0] if stats else (0, 0)

    return render_template(
        "manager.html",
        leads=leads,
        callers=callers,
        stats=stats
    )

@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/login")

    username = request.form["username"].strip()
    password = request.form["password"].strip()

    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'caller')
        ON CONFLICT DO NOTHING
    """, (username, generate_password_hash(password)), fetch=False)

    return redirect("/manager")

# ---------------- CALLER ----------------

@app.route("/caller/<caller_name>")
def caller_page(caller_name):
    if session.get("role") != "caller" or session.get("username") != caller_name:
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone
        FROM leads
        WHERE assigned_to=%s AND call_status='pending'
    """, (caller_name,))

    return render_template("caller.html", leads=leads, caller_name=caller_name)

@app.route("/start_call/<int:lead_id>", methods=["POST"])
def start_call(lead_id):
    query_db("UPDATE leads SET call_start_time=NOW() WHERE id=%s", (lead_id,), fetch=False)
    return jsonify({"status": "started"})

@app.route("/submit", methods=["POST"])
def submit():
    lead_id = request.form["lead_id"]
    remarks = request.form["remarks"]
    caller_name = request.form["caller_name"]

    query_db("""
        UPDATE leads
        SET
            call_end_time=NOW(),
            call_duration=EXTRACT(EPOCH FROM (NOW()-call_start_time))::INT,
            remarks=%s,
            call_status='completed'
        WHERE id=%s
    """, (remarks, lead_id), fetch=False)

    return redirect(f"/caller/{caller_name}")

# ---------------- START ----------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
