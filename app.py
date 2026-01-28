# =========================================================
# LEAD CALLING APP – FINAL ROLE-BASED VERSION
# Roles: ADMIN → MANAGER → CALLER
# =========================================================

import os
import psycopg2
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)
app.secret_key = "change-this-secret-key"


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


# =========================================================
# INITIAL DATABASE SETUP (SAFE TO RUN MULTIPLE TIMES)
# =========================================================

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
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            state_id INTEGER REFERENCES states(id),
            created_by INTEGER
        )
    """, fetch=False)

    query_db("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            name TEXT,
            phone TEXT,
            state_id INTEGER,
            manager_id INTEGER,
            caller_id INTEGER,
            call_status TEXT,
            remarks TEXT,
            call_attempt_time TIMESTAMP
        )
    """, fetch=False)


# =========================================================
# AUTHENTICATION ROUTES
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
            "SELECT id, password, role FROM users WHERE username=%s",
            (username,)
        )

        if not user or not check_password_hash(user[0][1], password):
            return render_template("login.html", error="Invalid credentials")

        session["user_id"] = user[0][0]
        session["username"] = username
        session["role"] = user[0][2]

        if user[0][2] == "admin":
            return redirect("/admin")
        elif user[0][2] == "manager":
            return redirect("/manager")
        else:
            return redirect("/caller")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# =========================================================
# SUPER ADMIN ROUTES
# =========================================================

@app.route("/create_super_admin")
def create_super_admin():
    password = generate_password_hash("admin123")
    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'admin')
        ON CONFLICT (username) DO NOTHING
    """, ("admin", password), fetch=False)
    return "Super Admin created (admin / admin123)"


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

    return render_template("admin.html", states=states, managers=managers)


@app.route("/create_manager", methods=["POST"])
def create_manager():
    if session.get("role") != "admin":
        return redirect("/login")

    username = request.form["username"].strip()
    password = generate_password_hash(request.form["password"])
    state_id = request.form["state_id"]

    query_db("""
        INSERT INTO users (username, password, role, state_id, created_by)
        VALUES (%s, %s, 'manager', %s, %s)
    """, (username, password, state_id, session["user_id"]), fetch=False)

    return redirect("/admin")


# =========================================================
# MANAGER ROUTES
# =========================================================

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    manager = query_db(
        "SELECT id, state_id FROM users WHERE id=%s",
        (session["user_id"],)
    )[0]

    callers = query_db("""
        SELECT id, username FROM users
        WHERE role='caller' AND created_by=%s
    """, (manager[0],))

    leads = query_db("""
        SELECT id, name, phone, call_status
        FROM leads
        WHERE manager_id=%s
        ORDER BY id DESC
    """, (manager[0],))

    return render_template("manager.html", callers=callers, leads=leads)


@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/login")

    username = request.form["username"].strip()
    password = generate_password_hash(request.form["password"])

    manager = query_db(
        "SELECT id, state_id FROM users WHERE id=%s",
        (session["user_id"],)
    )[0]

    query_db("""
        INSERT INTO users (username, password, role, state_id, created_by)
        VALUES (%s, %s, 'caller', %s, %s)
    """, (username, password, manager[1], manager[0]), fetch=False)

    return redirect("/manager")


# =========================================================
# CALLER ROUTES
# =========================================================

@app.route("/caller")
def caller():
    if session.get("role") != "caller":
        return redirect("/login")

    leads = query_db("""
        SELECT id, name, phone
        FROM leads
        WHERE caller_id=%s AND call_status='pending'
    """, (session["user_id"],))

    return render_template("caller.html", leads=leads)


@app.route("/mark_called/<int:lead_id>", methods=["POST"])
def mark_called(lead_id):
    if session.get("role") != "caller":
        return redirect("/login")

    query_db("""
        UPDATE leads
        SET call_attempt_time = NOW()
        WHERE id=%s AND caller_id=%s
    """, (lead_id, session["user_id"]), fetch=False)

    return {"status": "ok"}


@app.route("/submit", methods=["POST"])
def submit():
    if session.get("role") != "caller":
        return redirect("/login")

    lead_id = request.form["lead_id"]
    remarks = request.form["remarks"]

    query_db("""
        UPDATE leads
        SET remarks=%s, call_status='completed'
        WHERE id=%s AND caller_id=%s
    """, (remarks, lead_id, session["user_id"]), fetch=False)

    return redirect("/caller")


# =========================================================
# APP START
# =========================================================

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
