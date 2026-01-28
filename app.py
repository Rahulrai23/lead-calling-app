import psycopg2
import os
import pandas as pd
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

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
            SELECT username, password, role
            FROM users
            WHERE username = %s
        """, (username,))

        if not user:
            return render_template("login.html", error="Invalid credentials")

        if not check_password_hash(user[0][1], password):
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


@app.route("/create_admin")
def create_admin():
    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'manager')
        ON CONFLICT (username) DO NOTHING
    """, ("admin", generate_password_hash("admin123")), fetch=False)

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

    callers = query_db("""
        SELECT username FROM users WHERE role = 'caller'
    """)

    return render_template(
        "manager.html",
        leads=leads,
        callers=callers
    )


@app.route("/create_caller", methods=["POST"])
def create_caller_ui():
    if session.get("role") != "manager":
        return redirect("/login")

    username = request.form["username"].strip()
    raw_password = request.form["password"].strip()

    if not username or not raw_password:
        return "Username and password required"

    password = generate_password_hash(raw_password)

    query_db("""
        INSERT INTO users (username, password, role)
        VALUES (%s, %s, 'caller')
        ON CONFLICT (username) DO NOTHING
    """, (username, password), fetch=False)

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


@app.route("/add_lead", methods=["POST"])
def add_lead():
    if session.get("role") != "manager":
        return redirect("/login")

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
        UPDATE leads
        SET remarks=%s, call_status='completed'
        WHERE id=%s AND caller_id=%s
    """, (remarks, lead_id, session["user_id"]), fetch=False)
