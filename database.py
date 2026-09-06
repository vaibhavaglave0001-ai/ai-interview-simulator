"""SQLite persistence for users, questions, sessions, and answers."""

import csv
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database.db"
DATASET_PATH = BASE_DIR / "data" / "interview_questions.csv"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_connection() as connection:
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
        if connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0:
            with DATASET_PATH.open(newline="", encoding="utf-8") as csv_file:
                rows = [(row["question"], row["category"], row["difficulty"], row["ideal_answer"]) for row in csv.DictReader(csv_file)]
            connection.executemany(
                "INSERT INTO questions (question, category, difficulty, ideal_answer) VALUES (?, ?, ?, ?)",
                rows,
            )


def fetch_questions(category, difficulty):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM questions WHERE category = ? AND difficulty = ? ORDER BY RANDOM()",
            (category, difficulty),
        ).fetchall()
