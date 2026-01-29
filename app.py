import os, psycopg2, pandas as pd
from flask import Flask, render_template, request, redirect, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-in-prod"

# ---------------- DB ----------------

def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def q(query, params=(), fetch=True):
    con = get_db()
    cur = con.cursor()
    cur.execute(query, params)
    res = cur.fetchall() if fetch else None
    if not fetch:
        con.commit()
    cur.close()
    con.close()
    return res

def init_db():
    q("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        manager_id INTEGER
    )
    """, fetch=False)

    q("""
    CREATE TABLE IF NOT EXISTS leads(
        id SERIAL PRIMARY KEY,
        name TEXT,
        phone TEXT,
        manager_id INTEGER,
        caller_id INTEGER,
        status TEXT DEFAULT 'pending',
        remarks TEXT,
        call_start TIMESTAMP,
        call_end TIMESTAMP,
        duration INTEGER
    )
    """, fetch=False)

# ---------------- AUTH ----------------

@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        user = q("SELECT id,password,role FROM users WHERE username=%s",(u,))
        if not user or not check_password_hash(user[0][1], p):
            return render_template("login.html", error="Invalid login")

        session.clear()
        session["uid"] = user[0][0]
        session["role"] = user[0][2]

        return redirect(f"/{user[0][2]}")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/whoami")
def whoami():
    return jsonify(dict(session))

# ---------------- ADMIN ----------------

@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return redirect("/")

    managers = q("SELECT id,username FROM users WHERE role='manager'")
    return render_template("admin.html", managers=managers)

@app.route("/create_manager", methods=["POST"])
def create_manager():
    if session.get("role") != "admin":
        return redirect("/")

    q("""
    INSERT INTO users(username,password,role)
    VALUES(%s,%s,'manager')
    """, (
        request.form["username"],
        generate_password_hash(request.form["password"])
    ), fetch=False)

    return redirect("/admin")

# ---------------- MANAGER ----------------

@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/")

    callers = q(
        "SELECT id,username FROM users WHERE role='caller' AND manager_id=%s",
        (session["uid"],)
    )

    leads = q("""
    SELECT l.id,l.name,l.phone,u.username,l.status,l.duration
    FROM leads l
    LEFT JOIN users u ON l.caller_id=u.id
    WHERE l.manager_id=%s
    """, (session["uid"],))

    return render_template("manager.html", callers=callers, leads=leads)

@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/")

    q("""
    INSERT INTO users(username,password,role,manager_id)
    VALUES(%s,%s,'caller',%s)
    """, (
        request.form["username"],
        generate_password_hash(request.form["password"]),
        session["uid"]
    ), fetch=False)

    return redirect("/manager")

# ---------------- CALLER ----------------

@app.route("/caller")
def caller():
    if session.get("role") != "caller":
        return redirect("/")

    leads = q("""
    SELECT id,name,phone FROM leads
    WHERE caller_id=%s AND status='pending'
    """, (session["uid"],))

    return render_template("caller.html", leads=leads)

@app.route("/start/<int:id>")
def start(id):
    q("UPDATE leads SET call_start=NOW() WHERE id=%s",(id,),fetch=False)
    return redirect("/caller")

@app.route("/submit", methods=["POST"])
def submit():
    q("""
    UPDATE leads
    SET call_end=NOW(),
        duration=EXTRACT(EPOCH FROM NOW()-call_start),
        remarks=%s,
        status='completed'
    WHERE id=%s
    """, (request.form["remarks"], request.form["id"]), fetch=False)

    return redirect("/caller")

# ---------------- SEED ----------------

@app.route("/seed_admin")
def seed():
    q("DELETE FROM users", fetch=False)
    q("""
    INSERT INTO users(username,password,role)
    VALUES('admin',%s,'admin')
    """,(generate_password_hash("admin123"),),fetch=False)
    return "Admin ready → admin/admin123"

# ---------------- RUN ----------------

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
