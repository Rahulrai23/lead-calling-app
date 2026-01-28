# =========================================================
# LEAD CALLING APP – ROLE-BASED (ADMIN → MANAGER → CALLER)
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
# INITIAL DATABASE SETUP
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
# DEBUG / DIAGNOSTIC ROUTE (TEMPORARY)
# =========================================================

@app.route("/whoami")
def whoami():
    return {
        "user_id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role")
    }


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
    # 🔐 HARD GUARD WITH VISIBILITY
    if session.get("role") != "admin":
        return "ACCESS DENIED: Not admin", 403

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

    # ✅ If template missing, this text WILL show
    return render_template("admin.html", states=states, managers=managers)


@app.route("/create_manager", methods=["POST"])
def create_manager():
    if session.get("role") != "admin":
        return "ACCESS DENIED", 403

    username = request.form["username"].strip()
    password = generate_password_hash(request.form["password"])
    state_id = request.form["state_id"]

    query_db("""
        INSERT INTO users (username, password, role, state_id, created_by)
        VALUES (%s, %s, 'manager'
