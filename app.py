from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def get_db():
    return sqlite3.connect("database.db")

@app.route("/")
def login():
    return render_template("login.html")

@app.route("/caller")
def caller():
    db = get_db()
    leads = db.execute("""
        SELECT * FROM leads 
        WHERE assigned_to='caller1' 
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
        WHERE id=?
    """, (remarks, lead_id))
    db.commit()

    return redirect("/caller")

if __name__ == "__main__":
    app.run()

