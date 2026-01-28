import psycopg2
import os
from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret"


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


@app.route("/")
def home():
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = query_db(
            "SELECT username, password, role FROM users WHERE username=%s",
            (username,)
        )

        if not user or not check_password_hash(user[0][1], password):
            return "Invalid credentials"

        session["username"] = user[0][0]
        session["role"] = user[0][2]

        if user[0][2] == "manager":
            return redirect("/manager")

        return "Logged in as caller"

    return "Login Page"


@app.route("/manager")
def manager():
    if session.get("role") != "manager":
        return redirect("/login")

    return render_template("manager.html")


@app.route("/create_caller", methods=["POST"])
def create_caller():
    if session.get("role") != "manager":
        return redirect("/login")

    username = request.form["username"].strip()
    raw_password = request.form["password"].strip()

    if not username or not raw_password:
        return "Missing data"

    password = generate_password_hash(raw_password)

    query_db(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, 'caller')",
        (username, password),
        fetch=False
    )

    return "Caller created"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
