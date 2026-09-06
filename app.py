"""Flask entry point for the AI Interview Simulator."""

import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db
from models.answer_evaluator import evaluate_answer
from utils.question_selector import select_questions


app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-in-production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

with app.app_context():
    init_db()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to start an interview.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


@app.context_processor
def inject_user():
    return {"current_user": session.get("user_name")}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_connection() as connection:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], user_name=user["name"])
            return redirect(request.args.get("next") or url_for("interview_setup"))
        flash("Email or password is incorrect.", "danger")
    return render_template("login.html", mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email, and a password of at least 6 characters.", "danger")
        else:
            try:
                with get_connection() as connection:
                    connection.execute(
                        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                        (name, email, generate_password_hash(password)),
                    )
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "danger")
    return render_template("login.html", mode="register")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/interview/setup")
@login_required
def interview_setup():
    return render_template("index.html", setup_mode=True)


@app.route("/interview/start", methods=["POST"])
@login_required
def start_interview():
    category = request.form.get("category", "technical").lower()
    difficulty = request.form.get("difficulty", "easy").lower()
    try:
        requested_count = max(1, min(10, int(request.form.get("question_count", 5))))
    except ValueError:
        requested_count = 5
    selected = select_questions(category, difficulty, requested_count)
    if not selected:
        flash("No questions are available for that combination yet.", "warning")
        return redirect(url_for("interview_setup"))
    with get_connection() as connection:
        question_ids = []
        for item in selected:
            question = connection.execute(
                "SELECT id FROM questions WHERE question = ?", (item["question"],)
            ).fetchone()
            question_ids.append(question["id"])
        cursor = connection.execute(
            "INSERT INTO interview_sessions (user_id, category, difficulty, total_questions) VALUES (?, ?, ?, ?)",
            (session["user_id"], category, difficulty, len(question_ids)),
        )
        interview_id = cursor.lastrowid
    session["interview_id"] = interview_id
    session["question_ids"] = question_ids
    session["question_index"] = 0
    return redirect(url_for("interview_question", question_id=question_ids[0]))


@app.route("/interview/question/<int:question_id>")
@login_required
def interview_question(question_id):
    if question_id not in session.get("question_ids", []):
        return redirect(url_for("interview_setup"))
    with get_connection() as connection:
        question = connection.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    question_index = session.get("question_ids", []).index(question_id)
    return render_template(
        "interview.html",
        question=question,
        current_number=question_index + 1,
        total_questions=len(session.get("question_ids", [])),
    )


@app.route("/interview/submit", methods=["POST"])
@login_required
def submit_answer():
    question_id = int(request.form["question_id"])
    user_answer = request.form.get("answer", "").strip()
    with get_connection() as connection:
        question = connection.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        evaluation = evaluate_answer(user_answer, question["ideal_answer"])
        connection.execute(
            "INSERT INTO answers (session_id, question_id, user_answer, score, performance_level, suggestion) VALUES (?, ?, ?, ?, ?, ?)",
            (session["interview_id"], question_id, user_answer, evaluation["score"], evaluation["level"], evaluation["suggestion"]),
        )
    question_ids = session.get("question_ids", [])
    current_index = question_ids.index(question_id)
    if current_index + 1 < len(question_ids):
        return redirect(url_for("interview_question", question_id=question_ids[current_index + 1]))
    return redirect(url_for("result", interview_id=session["interview_id"]))


@app.route("/interview/end", methods=["POST"])
@login_required
def end_interview():
    return redirect(url_for("result", interview_id=session.get("interview_id")))


@app.route("/result/<int:interview_id>")
@login_required
def result(interview_id):
    with get_connection() as connection:
        interview = connection.execute(
            "SELECT * FROM interview_sessions WHERE id = ? AND user_id = ?",
            (interview_id, session["user_id"]),
        ).fetchone()
        answers = connection.execute(
            """SELECT answers.*, questions.question, questions.ideal_answer
               FROM answers JOIN questions ON questions.id = answers.question_id
               WHERE answers.session_id = ? ORDER BY answers.id""",
            (interview_id,),
        ).fetchall()
        if interview and not interview["completed_at"]:
            connection.execute(
                "UPDATE interview_sessions SET completed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), interview_id),
            )
    if not interview:
        flash("Interview not found.", "danger")
        return redirect(url_for("interview_setup"))
    scores = [answer["score"] for answer in answers]
    average_score = round(sum(scores) / len(scores), 1) if scores else 0
    if average_score >= 80:
        performance_level = "Excellent"
    elif average_score >= 60:
        performance_level = "Good"
    elif average_score >= 40:
        performance_level = "Needs Improvement"
    else:
        performance_level = "Poor"
    return render_template(
        "result.html",
        interview=interview,
        answers=answers,
        average_score=average_score,
        performance_level=performance_level,
    )


if __name__ == "__main__":
    app.run(debug=True)
