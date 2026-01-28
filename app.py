@app.route("/create_manager", methods=["POST"])
def create_manager():
    if session.get("role") != "admin":
        return "ACCESS DENIED", 403

    username = request.form["username"].strip()
    raw_password = request.form["password"]
    state_id = request.form["state_id"]

    if not username or not raw_password or not state_id:
        return "Missing data", 400

    password = generate_password_hash(raw_password)

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
        SELECT id, username
        FROM users
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
    raw_password = request.form["password"]

    if not username or not raw_password:
        return "Missing data", 400

    password = generate_password_hash(raw_password)

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
