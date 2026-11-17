"""Flask entry point for the AI Interview Simulator."""

import os
import secrets
import sqlite3
from datetime import datetime, timezone
from functools import wraps
from time import perf_counter
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db
from models.answer_evaluator import evaluate_answer, start_model_loading
from utils.question_selector import select_questions
from data.question_bank import DOMAINS


app = Flask(__name__)
PRODUCTION = os.environ.get("VERCEL") == "1"
if PRODUCTION and len(os.environ.get("SECRET_KEY", "")) < 32:
    raise RuntimeError("Set a persistent SECRET_KEY of at least 32 characters")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = PRODUCTION

QUESTION_COUNT_OPTIONS = {3, 5, 10}
INTERVIEW_SESSION_KEYS = (
    "interview_id",
    "question_ids",
    "question_index",
    "selected_question_count",
)

with app.app_context():
    init_db()

start_model_loading()


@app.before_request
def start_request_timer():
    g.request_started = perf_counter()
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "")
        if not expected or not secrets.compare_digest(expected.encode(), supplied.encode()):
            abort(400, description="Your form expired. Reload the page and try again.")


@app.after_request
def record_request_time(response):
    elapsed = (perf_counter() - g.request_started) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store"
    if PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if elapsed >= 1000:
        app.logger.warning("Slow request: %s %s %.1fms", request.method, request.path, elapsed)
    return response


@app.errorhandler(sqlite3.Error)
def database_unavailable(error):
    app.logger.error("Database request failed (%s)", type(error).__name__)
    return render_template("error.html", message="Your request could not be saved or loaded. Please try again shortly."), 503


@app.errorhandler(500)
def unexpected_error(error):
    return render_template("error.html", message="Something went wrong. Please try again shortly."), 500


def active_question_index():
    with get_connection() as connection:
        interview = connection.execute(
            "SELECT * FROM interview_sessions WHERE id = ? AND user_id = ? AND ended_at IS NULL",
            (session.get("interview_id"), session["user_id"]),
        ).fetchone()
        if not interview:
            clear_active_interview()
            return None
        sequence = connection.execute(
            "SELECT question_id FROM session_questions WHERE session_id = ? ORDER BY position",
            (interview["id"],),
        ).fetchall()
        if not sequence:
            # Preserve valid interviews opened before the schema upgrade. Old
            # repeated sequences cannot be repaired without changing the session.
            legacy_ids = session.get("question_ids", [])
            if len(legacy_ids) != interview["total_questions"] or len(set(legacy_ids)) != len(legacy_ids):
                clear_active_interview()
                flash("Please begin a new interview to use unique questions.", "warning")
                return None
            connection.executemany(
                "INSERT OR IGNORE INTO session_questions(session_id, question_id, position) VALUES (?, ?, ?)",
                [(interview["id"], question_id, position) for position, question_id in enumerate(legacy_ids)],
            )
            question_ids = legacy_ids
        else:
            question_ids = [row["question_id"] for row in sequence]
        session["question_ids"] = question_ids
        session["selected_question_count"] = interview["total_questions"]
        current_index = connection.execute(
            "SELECT COUNT(*) FROM answers WHERE session_id = ?", (interview["id"],)
        ).fetchone()[0]
    session["question_index"] = current_index
    return current_index


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
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return {"current_user": session.get("user_name"), "csrf_token": session["csrf_token"]}


def clear_active_interview():
    for key in INTERVIEW_SESSION_KEYS:
        session.pop(key, None)


def get_requested_question_count(form_value):
    try:
        requested_count = int(form_value)
    except (TypeError, ValueError):
        return None
    return requested_count if requested_count in QUESTION_COUNT_OPTIONS else None


def redirect_to_current_question():
    current_index = active_question_index()
    question_ids = session.get("question_ids", [])
    if current_index is None or not question_ids:
        return redirect(url_for("interview_setup"))
    if current_index >= len(question_ids):
        return redirect(url_for("result", interview_id=session["interview_id"]))
    return redirect(url_for("interview_question", question_id=question_ids[current_index]))


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
            next_path = request.args.get("next", "")
            try:
                parsed = urlsplit(next_path)
                safe_next = (
                    next_path.startswith("/")
                    and not next_path.startswith("//")
                    and not parsed.netloc
                    and not parsed.scheme
                    and "\\" not in next_path
                    and not any(ord(character) < 32 for character in next_path)
                )
            except ValueError:
                safe_next = False
            if not safe_next:
                next_path = url_for("index")
            return redirect(next_path)
        flash("Email or password is incorrect.", "danger")
    return render_template("login.html", mode="login")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or "@" not in email or not email.rsplit("@", 1)[-1] or len(password) < 6:
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


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/interview/setup")
@login_required
def interview_setup():
    return render_template("index.html", setup_mode=True, technical_domains=DOMAINS)


@app.route("/interview/start", methods=["POST"])
@login_required
def start_interview():
    category = request.form.get("category", "").strip().lower()
    difficulty = request.form.get("difficulty", "").strip().lower()
    requested_count = get_requested_question_count(request.form.get("question_count"))
    domain = request.form.get("domain", "python").strip().lower() if category == "technical" else ""
    if (category not in {"hr", "technical"} or difficulty not in {"easy", "medium", "hard"}
            or requested_count is None or (category == "technical" and domain not in DOMAINS)):
        flash("Choose an interview type, difficulty, and 3, 5, or 10 questions.", "warning")
        return redirect(url_for("interview_setup"))
    try:
        with get_connection() as connection:
            # Prefer questions outside this user's latest comparable interview.
            previous_ids = [row[0] for row in connection.execute(
                """SELECT question_id FROM session_questions WHERE session_id = (
                    SELECT id FROM interview_sessions WHERE user_id = ? AND category = ?
                    AND difficulty = ? AND domain = ? ORDER BY id DESC LIMIT 1
                )""", (session["user_id"], category, difficulty, domain),
            )]
        selected = select_questions(category, difficulty, requested_count, domain, previous_ids)
    except sqlite3.Error:
        app.logger.exception("Question pool lookup failed")
        flash("Questions could not be loaded. Please try again.", "warning")
        return redirect(url_for("interview_setup"))
    if len(selected) != requested_count:
        flash("No questions are available in sufficient unique numbers for that combination. Choose fewer questions or another domain.", "warning")
        return redirect(url_for("interview_setup"))
    try:
        with get_connection() as connection:
            question_ids = [item["id"] for item in selected]
            cursor = connection.execute(
                "INSERT INTO interview_sessions (user_id, category, difficulty, total_questions, domain) VALUES (?, ?, ?, ?, ?)",
                (session["user_id"], category, difficulty, requested_count, domain),
            )
            interview_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO session_questions (session_id, question_id, position) VALUES (?, ?, ?)",
                [(interview_id, question_id, position) for position, question_id in enumerate(question_ids)],
            )
    except sqlite3.Error:
        app.logger.exception("Interview creation failed")
        flash("Your interview could not be saved. Please try again.", "warning")
        return redirect(url_for("interview_setup"))
    session["interview_id"] = interview_id
    session["question_ids"] = question_ids
    session["question_index"] = 0
    session["selected_question_count"] = requested_count
    return redirect(url_for("interview_question", question_id=question_ids[0]))


@app.route("/interview/question/<int:question_id>")
@login_required
def interview_question(question_id):
    current_index = active_question_index()
    question_ids = session.get("question_ids", [])
    if current_index is None or not question_ids or question_id not in question_ids:
        return redirect(url_for("interview_setup"))
    if current_index >= len(question_ids):
        return redirect(url_for("result", interview_id=session["interview_id"]))
    position = question_ids.index(question_id)
    if position > current_index:
        return redirect(url_for("interview_question", question_id=question_ids[current_index]))
    with get_connection() as connection:
        question = connection.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        saved_answer = connection.execute(
            "SELECT user_answer FROM answers WHERE session_id = ? AND question_position = ?",
            (session["interview_id"], position),
        ).fetchone()
    if question is None:
        clear_active_interview()
        flash("This question is no longer available. Please start a new interview.", "warning")
        return redirect(url_for("interview_setup"))
    return render_template(
        "interview.html",
        question=question,
        question_position=position,
        current_number=position + 1,
        total_questions=session.get("selected_question_count", len(question_ids)),
        saved_answer=saved_answer["user_answer"] if saved_answer else None,
        previous_id=question_ids[position - 1] if position else None,
        next_id=question_ids[position + 1] if position < current_index else None,
        domain_label=DOMAINS.get(question["domain"], ""),
    )


@app.route("/interview/submit", methods=["POST"])
@login_required
def submit_answer():
    try:
        question_id = int(request.form["question_id"])
        question_position = int(request.form.get("question_position", -1))
        submitted_interview_id = int(request.form["interview_id"])
    except (KeyError, TypeError, ValueError):
        flash("Continue from your current interview question.", "warning")
        return redirect_to_current_question()
    user_answer = request.form.get("answer", "").strip()
    current_index = active_question_index()
    question_ids = session.get("question_ids", [])
    if (
        not question_ids
        or current_index is None
        or submitted_interview_id != session.get("interview_id")
        or question_position != current_index
        or current_index >= len(question_ids)
        or question_ids[current_index] != question_id
    ):
        flash("Continue from your current interview question.", "warning")
        return redirect_to_current_question()
    if not user_answer or len(user_answer) > 10000:
        flash("Enter an answer between 1 and 10,000 characters.", "warning")
        return redirect_to_current_question()
    with get_connection() as connection:
        question = connection.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    if question is None:
        clear_active_interview()
        return redirect(url_for("interview_setup"))
    evaluation = evaluate_answer(user_answer, question["ideal_answer"])
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO answers (session_id, question_id, user_answer, score, performance_level, suggestion, question_position, evaluation_method)
               SELECT ?, ?, ?, ?, ?, ?, ?, ?
               WHERE EXISTS (SELECT 1 FROM interview_sessions WHERE id = ? AND user_id = ? AND ended_at IS NULL)
               ON CONFLICT(session_id, question_position) DO NOTHING""",
            (session["interview_id"], question_id, user_answer, evaluation["score"], evaluation["level"], evaluation["suggestion"], current_index, evaluation["method"],
             session["interview_id"], session["user_id"]),
        )
    return redirect_to_current_question()


@app.route("/interview/end", methods=["POST"])
@login_required
def end_interview():
    interview_id = request.form.get("interview_id", type=int)
    if interview_id is None or interview_id != session.get("interview_id"):
        flash("Continue from your current interview question.", "warning")
        return redirect_to_current_question()
    with get_connection() as connection:
        connection.execute(
            "UPDATE interview_sessions SET ended_at = ? WHERE id = ? AND user_id = ? AND completed_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), interview_id, session["user_id"]),
        )
    clear_active_interview()
    flash("Interview ended before scoring. Start a new session when you are ready.", "info")
    return redirect(url_for("interview_setup"))


@app.route("/result/<int:interview_id>")
@login_required
def result(interview_id):
    with get_connection() as connection:
        interview = connection.execute(
            "SELECT * FROM interview_sessions WHERE id = ? AND user_id = ?",
            (interview_id, session["user_id"]),
        ).fetchone()
        if not interview or interview["ended_at"]:
            flash("Interview not found.", "danger")
            return redirect(url_for("interview_setup"))
        answers = connection.execute(
            """SELECT answers.*, questions.question, questions.ideal_answer
               FROM answers JOIN questions ON questions.id = answers.question_id
               WHERE answers.session_id = ? ORDER BY answers.question_position, answers.id""",
            (interview_id,),
        ).fetchall()
        if len(answers) < interview["total_questions"]:
            flash("Complete all selected questions before viewing results.", "warning")
            if interview_id == session.get("interview_id"):
                return redirect_to_current_question()
            return redirect(url_for("interview_setup"))
        if not interview["completed_at"]:
            connection.execute(
                "UPDATE interview_sessions SET completed_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), interview_id),
            )
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
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
