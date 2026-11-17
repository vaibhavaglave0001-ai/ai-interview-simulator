"""SQLite persistence for users, questions, sessions, and answers."""

import csv
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep

from data.question_bank import bank_rows


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database.db"
DATASET_PATH = BASE_DIR / "data" / "interview_questions.csv"


@contextmanager
def get_connection():
    if os.environ.get("TURSO_DATABASE_URL"):
        from remote_database import remote_connection
        with remote_connection() as connection:
            yield connection
        return
    if os.environ.get("VERCEL") == "1":
        raise RuntimeError("Hosted database is required on Vercel")
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _enable_wal(connection):
    deadline = monotonic() + 10
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL").fetchone()
            return
        except sqlite3.OperationalError as error:
            if error.sqlite_errorcode != sqlite3.SQLITE_BUSY or monotonic() >= deadline:
                raise
            sleep(0.05)


def init_db():
    if os.environ.get("TURSO_DATABASE_URL"):
        # Provision/migrate explicitly, never reseed on every cold start.
        with get_connection() as connection:
            connection.execute("SELECT question_position, evaluation_method FROM answers LIMIT 0")
            connection.execute("SELECT domain, topic FROM questions LIMIT 0")
            connection.execute("SELECT ended_at, domain FROM interview_sessions LIMIT 0")
            connection.execute("SELECT position FROM session_questions LIMIT 0")
        return
    with get_connection() as connection:
        _enable_wal(connection)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                ideal_answer TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                user_answer TEXT NOT NULL,
                score REAL NOT NULL,
                performance_level TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES interview_sessions (id),
                FOREIGN KEY (question_id) REFERENCES questions (id)
            );
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        answer_columns = {row["name"] for row in connection.execute("PRAGMA table_info(answers)")}
        if "question_position" not in answer_columns:
            connection.execute("ALTER TABLE answers ADD COLUMN question_position INTEGER")
        if "evaluation_method" not in answer_columns:
            connection.execute("ALTER TABLE answers ADD COLUMN evaluation_method TEXT NOT NULL DEFAULT 'legacy'")
        session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(interview_sessions)")}
        if "ended_at" not in session_columns:
            connection.execute("ALTER TABLE interview_sessions ADD COLUMN ended_at TEXT")
        if "domain" not in session_columns:
            connection.execute("ALTER TABLE interview_sessions ADD COLUMN domain TEXT NOT NULL DEFAULT ''")
        question_columns = {row["name"] for row in connection.execute("PRAGMA table_info(questions)")}
        for column in ("domain", "topic"):
            if column not in question_columns:
                connection.execute(f"ALTER TABLE questions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS session_questions (
                session_id INTEGER NOT NULL REFERENCES interview_sessions(id),
                question_id INTEGER NOT NULL REFERENCES questions(id),
                position INTEGER NOT NULL CHECK(position >= 0),
                PRIMARY KEY (session_id, position),
                UNIQUE (session_id, question_id)
            )
        """)
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS answers_session_position ON answers (session_id, question_position)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS questions_category_difficulty ON questions (category, difficulty)"
        )
        if connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
            with DATASET_PATH.open(newline="", encoding="utf-8") as csv_file:
                rows = [(row["question"], row["category"], row["difficulty"], row["ideal_answer"]) for row in csv.DictReader(csv_file)]
            connection.executemany(
                "INSERT INTO questions (question, category, difficulty, ideal_answer) VALUES (?, ?, ?, ?)",
                rows,
            )
        # Upgrade existing databases too; never replace rows referenced by results.
        connection.executemany(
            """INSERT INTO questions (question, category, difficulty, ideal_answer, domain, topic)
               SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS (
                   SELECT 1 FROM questions WHERE question = ? AND category = ?
                   AND difficulty = ? AND domain = ?
               )""",
            [(*row, row[0], row[1], row[2], row[4]) for row in bank_rows()],
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS questions_domain_pool ON questions(category, difficulty, domain)"
        )


def fetch_questions(category, difficulty, domain=None):
    with get_connection() as connection:
        return connection.execute(
            """SELECT * FROM questions WHERE category = ? AND difficulty = ?
               AND domain = ? AND (category != 'hr' OR topic != '') ORDER BY id""",
            (category, difficulty, (domain or "python") if category == "technical" else ""),
        ).fetchall()
