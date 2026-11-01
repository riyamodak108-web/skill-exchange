from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
import sqlite3
from werkzeug.security import (
    generate_password_hash, check_password_hash
)

app = Flask(__name__)
app.secret_key = "skill-exchange-secret"

DATABASE = "skillswap.db"


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# REGISTRATION
@app.route("/register", methods=["GET", "POST"])
def register():
    message = ""

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            message = "Please fill in all fields."

        else:
            hashed_password = generate_password_hash(password)
            connection = get_db_connection()

            try:
                connection.execute(
                    """INSERT INTO users (name, email, password)
                       VALUES (?, ?, ?)""",
                    (name, email, hashed_password)
                )
                connection.commit()
                message = "Registration successful! Please log in."

            except sqlite3.IntegrityError:
                message = "This email is already registered."

            finally:
                connection.close()

    return render_template("register.html", message=message)


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        connection = get_db_connection()

        try:
            user = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()
        finally:
            connection.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


# DASHBOARD
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        name=session["user_name"]
    )

    
@app.route("/skills", methods=["GET", "POST"])
def skills():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    if request.method == "POST":
        skill_name = request.form.get("skill_name", "").strip()
        skill_type = request.form.get("skill_type", "")

        if not skill_name:
            flash("Please enter a skill name.")

        elif skill_type not in ("teach", "learn"):
            flash("Please select a valid skill type.")

        else:
            connection.execute(
                """
                INSERT INTO skills (user_id, skill_name, skill_type)
                VALUES (?, ?, ?)
                """,
                (session["user_id"], skill_name, skill_type)
            )
            connection.commit()
            flash("Skill added successfully!")

    user_skills = connection.execute(
        """
        SELECT id, skill_name, skill_type
        FROM skills
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (session["user_id"],)
    ).fetchall()

    connection.close()

    return render_template(
        "skills.html",
        skills=user_skills,
        name=session["user_name"]
    )

@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()

    user = conn.execute(    
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    total_skills = conn.execute(
        "SELECT COUNT(*) AS count FROM skills WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()["count"]

    teaching_skills = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM skills
        WHERE user_id = ? AND skill_type = 'teach'
        """,
        (session["user_id"],)
    ).fetchone()["count"]

    learning_skills = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM skills
        WHERE user_id = ? AND skill_type = 'learn'
        """,
        (session["user_id"],)
    ).fetchone()["count"]

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        total_skills=total_skills,
        teaching_skills=teaching_skills,
        learning_skills=learning_skills
    )


@app.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()

        if not name or not email:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()
            conn.close()
            return render_template(
                "edit_profile.html",
                user=user,
                error="Name and email are required."
            )

        try:
            conn.execute(
                "UPDATE users SET name = ?, email = ? WHERE id = ?",
                (name, email, session["user_id"])
            )
            conn.commit()
        except sqlite3.IntegrityError:
            user = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()
            conn.close()
            return render_template(
                "edit_profile.html",
                user=user,
                error="That email address is already registered."
            )

        conn.close()
        return redirect("/profile")

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    conn.close()
    return render_template("edit_profile.html", user=user)


@app.route("/browse")
def browse_skills():
    if "user_id" not in session:
        return redirect(url_for("login"))

    search_query = request.args.get("q", "").strip()

    connection = get_db_connection()

    try:
        browse_results = connection.execute(
            """
            SELECT
                skills.id,
                skills.skill_name,
                skills.skill_type,
                users.name AS student_name
            FROM skills
            JOIN users ON skills.user_id = users.id
            WHERE skills.user_id != ?
              AND skills.skill_name LIKE ?
            ORDER BY skills.skill_name COLLATE NOCASE
            """,
            (session["user_id"], "%" + search_query + "%")
        ).fetchall()
    finally:
        connection.close()

    return render_template(
        "browse.html",
        skills=browse_results,
        search_query=search_query,
        name=session["user_name"]
    )


@app.route("/request_exchange/<int:skill_id>", methods=["POST"])
def request_exchange(skill_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    sender_id = session["user_id"]
    connection = get_db_connection()

    try:
        skill = connection.execute(
            "SELECT id, user_id, skill_name, skill_type FROM skills WHERE id = ?",
            (skill_id,)
        ).fetchone()

        if skill is None:
            flash("That skill could not be found.")
        elif skill["user_id"] == sender_id:
            flash("You cannot request your own skill.")
        elif skill["skill_type"] != "teach":
            flash("You can only request skills that another student can teach.")
        else:
            existing_request = connection.execute(
                """
                SELECT id FROM exchange_requests
                WHERE sender_id = ? AND skill_id = ? AND status = 'pending'
                """,
                (sender_id, skill_id)
            ).fetchone()

            if existing_request:
                flash("You already have a pending request for this skill.")
            else:
                connection.execute(
                    """
                    INSERT INTO exchange_requests
                        (sender_id, receiver_id, skill_id, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (sender_id, skill["user_id"], skill_id)
                )
                connection.commit()
                flash("Skill exchange request sent!")

    finally:
        connection.close()

    return redirect(url_for("browse_skills"))


@app.route("/requests")
def requests_page():
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    try:
        all_requests = connection.execute(
            "SELECT * FROM exchange_requests"
        ).fetchall()

        print("ALL SAVED REQUESTS:")
        for req in all_requests:
            print(dict(req))

        incoming_requests = connection.execute(
            """
            SELECT
                exchange_requests.id,
                exchange_requests.status,
                users.name AS sender_name,
                skills.skill_name
            FROM exchange_requests
            JOIN users
                ON exchange_requests.sender_id = users.id
            JOIN skills
                ON exchange_requests.skill_id = skills.id
            WHERE exchange_requests.receiver_id = ?
            ORDER BY exchange_requests.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

        print("Logged-in user ID:", session["user_id"])
        print("Incoming requests found:", len(incoming_requests))

    finally:
        connection.close()

    return render_template(
        "requests.html",
        requests=incoming_requests,
        name=session["user_name"]
    )



@app.route("/respond_request/<int:request_id>/<action>", methods=["POST"])
def respond_request(request_id, action):
    if "user_id" not in session:
        return redirect(url_for("login"))

    if action not in ("accepted", "rejected"):
        return redirect(url_for("requests_page"))

    connection = get_db_connection()

    try:
        result = connection.execute(
            """
            UPDATE exchange_requests
            SET status = ?
            WHERE id = ?
              AND receiver_id = ?
              AND status = 'pending'
            """,
            (action, request_id, session["user_id"])
        )

        connection.commit()

        if result.rowcount == 1:
            flash("Request " + action + " successfully!")
        else:
            flash("Request not found or already responded to.")
    finally:
        connection.close()

    return redirect(url_for("requests_page"))



@app.route("/skills/delete/<int:skill_id>", methods=["POST"])
def delete_skill(skill_id):
    # Only logged-in users can delete skills
    if "user_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    try:
        # Delete only if the skill belongs to the logged-in user
        cursor = connection.execute(
            """
            DELETE FROM skills
            WHERE id = ? AND user_id = ?
            """,
            (skill_id, session["user_id"])
        )

        connection.commit()

        if cursor.rowcount == 1:
            flash("Skill deleted successfully!")
        else:
            flash("Skill not found or you do not have permission to delete it.")

    finally:
        connection.close()

    return redirect(url_for("skills"))

# LOGOUT
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))




if __name__ == "__main__":
    app.run(debug=True)
app = Flask(__name__)
print("APP LOCATION:", app.root_path)