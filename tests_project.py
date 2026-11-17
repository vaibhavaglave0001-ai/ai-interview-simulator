"""Offline route, persistence, concurrency, scoring, and latency regressions."""

import importlib
import os
import sqlite3
import statistics
import tempfile
import time
import unittest
from html.parser import HTMLParser
from html import unescape
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

import database
from tests_smoke import FormClient, _complete_session, _start_session
from data.question_bank import DOMAINS, bank_rows
from utils.question_selector import normalize_question, select_questions


class NavigationParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.forms = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a":
            self.links.append(attributes.get("href"))
        if tag == "form" and attributes.get("id"):
            self.forms[attributes["id"]] = attributes


class ProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf"})
        cls.environment.start()
        cls.directory = tempfile.TemporaryDirectory()
        cls.database_patch = patch.object(database, "DATABASE_PATH", os.path.join(cls.directory.name, "startup.db"))
        cls.database_patch.start()
        cls.module = importlib.import_module("app")
        cls.app = cls.module.app
        cls.app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
        cls.app.test_client_class = FormClient

    @classmethod
    def tearDownClass(cls):
        cls.database_patch.stop()
        cls.directory.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(database, "DATABASE_PATH", os.path.join(self.directory.name, "test.db"))
        self.database_patch.start()
        database.init_db()
        self.client = self.app.test_client()
        self.client.post("/register", data={"name": "Test User", "email": "test@example.com", "password": "secret1"})
        self.client.post("/login", data={"email": "test@example.com", "password": "secret1"})

    def tearDown(self):
        self.database_patch.stop()
        self.directory.cleanup()

    def state(self):
        with self.client.session_transaction() as state:
            return dict(state)

    def answer_data(self):
        state = self.state()
        return {"interview_id": state["interview_id"], "question_id": state["question_ids"][state["question_index"]], "question_position": state["question_index"], "answer": "I explain my relevant skills with a specific example and result."}

    def test_all_interview_combinations_with_real_fallback(self):
        for category in ("technical", "hr"):
            for difficulty in ("easy", "medium", "hard"):
                for count in (3, 5, 10):
                    with self.subTest(category=category, difficulty=difficulty, count=count):
                        response = self.client.post("/interview/start", data={"category": category, "difficulty": difficulty, "question_count": count})
                        self.assertEqual(response.status_code, 302)
                        state = self.state()
                        _complete_session(self.client, state["interview_id"], count)
                        with database.get_connection() as connection:
                            rows = connection.execute("SELECT * FROM answers WHERE session_id = ?", (state["interview_id"],)).fetchall()
                            self.assertEqual(len(rows), count)
                            self.assertTrue(all(0 <= row["score"] <= 100 for row in rows))
                            self.assertTrue(all(row["evaluation_method"] == "tfidf-fallback" for row in rows))
                            self.assertEqual(len({row["question_position"] for row in rows}), count)

    def test_every_domain_count_and_difficulty_has_unique_stable_navigation(self):
        from tests_smoke import _fake_evaluator
        for category, domain in [("hr", "")] + [("technical", key) for key in DOMAINS]:
            for difficulty in ("easy", "medium", "hard"):
                for count in (3, 5, 10):
                    with self.subTest(category=category, domain=domain, difficulty=difficulty, count=count), patch.object(self.module, "evaluate_answer", _fake_evaluator):
                        self.client.post("/interview/start", data={"category": category, "domain": domain, "difficulty": difficulty, "question_count": count})
                        state = self.state()
                        ids = state["question_ids"]
                        self.assertEqual(len(ids), count)
                        self.assertEqual(len(set(ids)), count)
                        with database.get_connection() as connection:
                            rows = connection.execute("""SELECT q.* FROM session_questions sq JOIN questions q ON q.id = sq.question_id
                                WHERE sq.session_id = ? ORDER BY sq.position""", (state["interview_id"],)).fetchall()
                        self.assertEqual([row["id"] for row in rows], ids)
                        self.assertEqual(len({normalize_question(row["question"]) for row in rows}), count)
                        self.assertEqual(len({row["topic"] for row in rows}), count)
                        self.assertTrue(all(row["domain"] == domain for row in rows))
                        for position, question_id in enumerate(ids):
                            path = f"/interview/question/{question_id}"
                            page = self.client.get(path)
                            self.assertIn(f"Question {position + 1} of {count}".encode(), page.data)
                            self.assertIn(rows[position]["question"], unescape(page.get_data(as_text=True)))
                            if position:
                                previous = self.client.get(f"/interview/question/{ids[position - 1]}")
                                self.assertIn(b"readonly", previous.data)
                                self.assertIn(b"A saved answer", previous.data)
                                self.assertIn(f'href="{path}"'.encode(), previous.data)
                                self.assertIn(f"Question {position + 1} of {count}".encode(), self.client.get(path).data)
                                self.assertEqual(self.state()["question_ids"], ids)
                            self.client.post("/interview/submit", data={"interview_id": state["interview_id"], "question_id": question_id,
                                "question_position": position, "answer": "A saved answer"})
                        result = self.client.get(f'/result/{state["interview_id"]}')
                        self.assertEqual(result.data.count(b'class="answer-review"'), count)

    def test_duplicate_pool_is_filtered_and_insufficient_pool_never_padded(self):
        rows = [dict(id=index, question=text, ideal_answer="Guidance", topic=str(index)) for index, text in enumerate(
            ["Explain teamwork?", " EXPLAIN teamwork!!! ", "Explain leadership?", "Explain conflict?", "", "Explain teamwork?"])]
        with patch("utils.question_selector.fetch_questions", return_value=rows):
            selected = select_questions("hr", "easy", 3)
            self.assertEqual(len(selected), 3)
            self.assertEqual(len({normalize_question(row["question"]) for row in selected}), 3)
            self.assertEqual(select_questions("hr", "easy", 5), [])
        # Duplicate IDs are rejected even when wording differs.
        rows = [dict(id=identifier, question=text, ideal_answer="Guidance", topic=str(index))
            for index, (identifier, text) in enumerate([(1, "First concept?"), (1, "Second concept?"), (2, "Third concept?")])]
        with patch("utils.question_selector.fetch_questions", return_value=rows):
            self.assertEqual(select_questions("hr", "easy", 3), [])

    def test_new_session_changes_set_and_cookie_cannot_reset_sequence(self):
        for count in (3, 5, 10):
            _start_session(self.client, count)
            old_ids = self.state()["question_ids"]
            _start_session(self.client, count)
            new_ids = self.state()["question_ids"]
            self.assertNotEqual(set(old_ids), set(new_ids))
            with self.client.session_transaction() as state:
                state["question_ids"] = list(reversed(new_ids))
                state["selected_question_count"] = 100
            page = self.client.get(f"/interview/question/{new_ids[0]}")
            self.assertIn(f"Question 1 of {count}".encode(), page.data)
            self.assertEqual(self.state()["question_ids"], new_ids)

    def test_invalid_domain_and_insufficient_pool_keep_active_session(self):
        interview_id = _start_session(self.client, 3)
        settings = dict(category="technical", difficulty="easy", question_count=10, domain="unknown")
        response = self.client.post("/interview/start", data=settings, follow_redirects=True)
        self.assertIn(b'role="alert"', response.data)
        self.assertEqual(self.state()["interview_id"], interview_id)
        with database.get_connection() as connection:
            connection.execute("DELETE FROM questions WHERE domain = 'java' AND id NOT IN (SELECT MIN(id) FROM questions WHERE domain = 'java' GROUP BY difficulty)")
        response = self.client.post("/interview/start", data={**settings, "domain": "java"}, follow_redirects=True)
        self.assertIn(b"sufficient unique", response.data)
        self.assertEqual(self.state()["interview_id"], interview_id)

    def test_question_loading_and_save_errors_are_recoverable(self):
        interview_id = _start_session(self.client, 3)
        settings = dict(category="hr", difficulty="easy", question_count=5)
        with patch.object(self.module, "select_questions", side_effect=sqlite3.OperationalError("pool unavailable")), self.assertLogs(self.module.app.logger, level="ERROR"):
            response = self.client.post("/interview/start", data=settings, follow_redirects=True)
        self.assertIn(b"Questions could not be loaded", response.data)
        self.assertEqual(self.state()["interview_id"], interview_id)
        with database.get_connection() as connection:
            connection.execute("""CREATE TRIGGER reject_new_session BEFORE INSERT ON interview_sessions
                BEGIN SELECT RAISE(ABORT, 'test storage error'); END""")
        with self.assertLogs(self.module.app.logger, level="ERROR"):
            response = self.client.post("/interview/start", data=settings, follow_redirects=True)
        self.assertIn(b"could not be saved", response.data)
        self.assertEqual(self.state()["interview_id"], interview_id)

    def test_legacy_repeated_session_requests_restart_without_changing_answers(self):
        interview_id = _start_session(self.client, 3)
        with database.get_connection() as connection:
            connection.execute("DELETE FROM session_questions WHERE session_id = ?", (interview_id,))
        with self.client.session_transaction() as state:
            question_id = state["question_ids"][0]
            state["question_ids"] = [question_id] * 3
        response = self.client.get(f"/interview/question/{question_id}", follow_redirects=True)
        self.assertIn(b"begin a new interview", response.data)
        self.assertNotIn("interview_id", self.state())

    def test_session_question_constraints_enforce_unique_ids_and_positions(self):
        interview_id = _start_session(self.client, 3)
        ids = self.state()["question_ids"]
        with database.get_connection() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO session_questions VALUES (?, ?, ?)", (interview_id, ids[0], 3))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO session_questions VALUES (?, ?, ?)", (interview_id, ids[1], 0))

    def test_future_question_cannot_skip_current_and_foreign_question_is_rejected(self):
        _start_session(self.client, 3)
        ids = self.state()["question_ids"]
        self.assertEqual(self.client.get(f"/interview/question/{ids[-1]}").location, f"/interview/question/{ids[0]}")
        self.assertEqual(self.client.get("/interview/question/999999").location, "/interview/setup")

    def test_bank_upgrade_adds_questions_without_changing_existing_ids(self):
        with database.get_connection() as connection:
            original = [tuple(row) for row in connection.execute("SELECT id, question FROM questions")]
        database.init_db()
        with database.get_connection() as connection:
            upgraded = [tuple(row) for row in connection.execute("SELECT id, question FROM questions")]
        self.assertEqual(original, upgraded)
        self.assertEqual(len(list(bank_rows())), 405)

    def test_registration_login_and_logout_validation(self):
        response = self.client.post("/register", data={"name": "Duplicate", "email": "TEST@example.com", "password": "secret1"})
        self.assertIn(b"already exists", response.data)
        response = self.client.post("/register", data={"name": "Bad", "email": "invalid", "password": "secret1"})
        self.assertIn(b"valid email", response.data)
        self.client.post("/logout")
        self.assertEqual(self.client.get("/interview/setup").status_code, 302)
        response = self.client.post("/login", data={"email": "test@example.com", "password": "wrong"})
        self.assertIn(b"incorrect", response.data)
        self.assertEqual(self.client.get("/logout").status_code, 405)

    def test_login_redirect_validation_and_form_destination(self):
        self.client.post("/logout")
        response = self.client.get("/login?next=/interview/setup")
        self.assertIn(b'action="/login?next=/interview/setup"', response.data)
        for target in ("https://example.com", "//example.com", "/\\example.com", "javascript:alert(1)", "//[", "/\nexample"):
            response = self.client.post("/login", query_string={"next": target}, data={"email": "test@example.com", "password": "secret1"})
            self.assertEqual(response.location, "/")
        response = self.client.post("/login?next=/interview/setup", data={"email": "test@example.com", "password": "secret1"})
        self.assertEqual(response.location, "/interview/setup")

    def test_login_dashboard_setup_questions_navigation(self):
        self.client.post("/logout")
        response = self.client.post("/login", data={"email": "test@example.com", "password": "secret1"})
        self.assertEqual(response.location, "/")
        dashboard = self.client.get(response.location)
        parser = NavigationParser()
        parser.feed(dashboard.get_data(as_text=True))
        self.assertIn("/interview/setup", parser.links)
        self.assertNotIn("setup-form", parser.forms)
        self.assertIn(b"Start an interview", dashboard.data)
        setup = self.client.get("/interview/setup")
        parser = NavigationParser()
        parser.feed(setup.get_data(as_text=True))
        self.assertEqual(parser.forms["setup-form"]["action"], "/interview/start")
        self.assertEqual(parser.forms["setup-form"]["method"], "post")
        self.assertIn(b"Set the room.", setup.data)
        self.assertNotIn(b"hero-section", setup.data)
        response = self.client.post(parser.forms["setup-form"]["action"], data={"category": "hr", "difficulty": "hard", "question_count": 3})
        self.assertTrue(response.location.startswith("/interview/question/"))
        first_question = self.client.get(response.location)
        self.assertIn(b"Question 1 of 3", first_question.data)
        self.assertIn(b"HR", first_question.data)
        self.assertIn(b"Hard", first_question.data)
        with database.get_connection() as connection:
            interview = connection.execute("SELECT * FROM interview_sessions WHERE id = ?", (self.state()["interview_id"],)).fetchone()
            self.assertEqual((interview["category"], interview["difficulty"], interview["total_questions"]), ("hr", "hard", 3))
        response = self.client.post("/interview/submit", data=self.answer_data(), follow_redirects=True)
        self.assertIn(b"Question 2 of 3", response.data)

    def test_protected_navigation_requires_login(self):
        self.client.post("/logout")
        for path in ("/interview/setup", "/interview/question/1", "/result/1"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.startswith("/login?next="))
        for path in ("/interview/start", "/interview/submit", "/interview/end"):
            response = self.client.post(path)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.startswith("/login?next="))

    def test_csrf_is_required(self):
        self.assertEqual(self.client.open("/interview/start", method="POST", data={}).status_code, 400)
        self.assertEqual(self.client.open("/logout", method="POST", data={"csrf_token": "wrong"}).status_code, 400)
        self.assertEqual(self.client.open("/logout", method="POST", data={"csrf_token": "日本語"}).status_code, 400)

    def test_old_tab_cannot_answer_new_interview(self):
        _start_session(self.client, 3)
        old_data = self.answer_data()
        _start_session(self.client, 3)
        self.client.post("/interview/submit", data=old_data)
        self.assertEqual(self.state()["question_index"], 0)

    def test_old_tab_cannot_end_new_interview(self):
        old_interview_id = _start_session(self.client, 3)
        new_interview_id = _start_session(self.client, 3)
        self.client.post("/interview/end", data={"interview_id": old_interview_id})
        self.assertEqual(self.state()["interview_id"], new_interview_id)
        with database.get_connection() as connection:
            self.assertIsNone(connection.execute("SELECT ended_at FROM interview_sessions WHERE id = ?", (new_interview_id,)).fetchone()[0])
        self.client.post("/interview/end", data={"interview_id": new_interview_id})
        self.assertNotIn("interview_id", self.state())

    def test_invalid_setup_does_not_start_an_interview(self):
        settings = {"category": "technical", "difficulty": "easy", "question_count": 5}
        invalid_settings = [{**settings, "category": "unknown"}]
        invalid_settings.extend({**settings, "question_count": count} for count in ("invalid", "4", "-1", ""))
        invalid_settings.extend({key: value for key, value in settings.items() if key != missing} for missing in settings)
        for invalid in invalid_settings:
            response = self.client.post("/interview/start", data=invalid, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.request.path.endswith("/interview/setup"))
            self.assertIn(b'role="alert"', response.data)
            self.assertNotIn("interview_id", self.state())
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM interview_sessions").fetchone()[0], 0)

    def test_unavailable_pool_keeps_existing_interview(self):
        interview_id = _start_session(self.client, 3)
        with database.get_connection() as connection:
            connection.execute("DELETE FROM questions WHERE category = 'technical' AND difficulty = 'hard'")
        response = self.client.post("/interview/start", data={"category": "technical", "difficulty": "hard", "question_count": 5}, follow_redirects=True)
        self.assertIn(b"No questions are available", response.data)
        self.assertEqual(self.state()["interview_id"], interview_id)

    def test_blank_oversized_and_malformed_answers_do_not_advance(self):
        _start_session(self.client, 3)
        data = self.answer_data()
        for answer in ("", "   ", "x" * 10001):
            self.client.post("/interview/submit", data={**data, "answer": answer})
            self.assertEqual(self.state()["question_index"], 0)
        for invalid in ({}, {**data, "question_id": "bad"}, {**data, "question_position": -1}, {**data, "question_id": 99999}):
            self.assertEqual(self.client.post("/interview/submit", data=invalid).status_code, 302)
            self.assertEqual(self.state()["question_index"], 0)
        response = self.client.post("/interview/submit", data={**data, "answer": "x" * 70000})
        self.assertEqual(response.status_code, 413)

    def test_duplicate_cookie_replay_does_not_insert_twice(self):
        interview_id = _start_session(self.client, 3)
        data = self.answer_data()
        old_cookie = self.client.get_cookie("session").value
        self.client.post("/interview/submit", data=data)
        self.client.set_cookie("session", old_cookie)
        self.client.post("/interview/submit", data=data)
        self.assertEqual(self.state()["question_index"], 1)
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM answers WHERE session_id = ?", (interview_id,)).fetchone()[0], 1)
        self.assertEqual(self.client.get(f"/result/{interview_id}").status_code, 302)

    def test_concurrent_duplicate_submissions(self):
        interview_id = _start_session(self.client, 3)
        data = self.answer_data()
        cookie = self.client.get_cookie("session").value
        barrier = Barrier(2)
        from models.answer_evaluator import evaluate_answer

        def synchronized_evaluation(*args):
            barrier.wait(timeout=10)
            return evaluate_answer(*args)

        def submit():
            client = self.app.test_client()
            client.set_cookie("session", cookie)
            return client.post("/interview/submit", data=data).status_code

        with patch.object(self.module, "evaluate_answer", side_effect=synchronized_evaluation):
            with ThreadPoolExecutor(max_workers=2) as executor:
                self.assertEqual(list(executor.map(lambda unused: submit(), range(2))), [302, 302])
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM answers WHERE session_id = ?", (interview_id,)).fetchone()[0], 1)

    def test_parallel_interviews_complete_without_database_errors(self):
        user_id = self.state()["user_id"]

        def complete(unused):
            client = self.app.test_client()
            with client.session_transaction() as state:
                state.update(user_id=user_id, user_name="Parallel Test")
            interview_id = _start_session(client, 5)
            _complete_session(client, interview_id, 5)
            return interview_id

        with ThreadPoolExecutor(max_workers=4) as executor:
            interview_ids = list(executor.map(complete, range(4)))
        self.assertEqual(len(set(interview_ids)), 4)
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0], 20)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_ended_session_rejects_old_cookie(self):
        interview_id = _start_session(self.client, 3)
        data = self.answer_data()
        cookie = self.client.get_cookie("session").value
        self.client.post("/interview/end", data={"interview_id": interview_id})
        self.client.set_cookie("session", cookie)
        response = self.client.post("/interview/submit", data=data)
        self.assertEqual(response.location, "/interview/setup")
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM answers WHERE session_id = ?", (interview_id,)).fetchone()[0], 0)

    def test_result_ownership_and_missing_results(self):
        interview_id = _start_session(self.client, 3)
        _complete_session(self.client, interview_id, 3)
        other = self.app.test_client()
        other.post("/register", data={"name": "Other", "email": "other@example.com", "password": "secret1"})
        other.post("/login", data={"email": "other@example.com", "password": "secret1"})
        self.assertEqual(other.get(f"/result/{interview_id}").location, "/interview/setup")
        self.assertEqual(other.get("/result/99999").location, "/interview/setup")

    def test_completed_session_redirects_stale_submissions_to_results(self):
        interview_id = _start_session(self.client, 3)
        data = self.answer_data()
        cookie = self.client.get_cookie("session").value
        _complete_session(self.client, interview_id, 3)
        self.client.set_cookie("session", cookie)
        response = self.client.post("/interview/submit", data=data)
        self.assertEqual(response.location, f"/result/{interview_id}")

    def test_database_is_question_source_and_handles_removed_question(self):
        with database.get_connection() as connection:
            connection.execute("DELETE FROM questions WHERE category = 'hr' AND difficulty = 'easy'")
            for index in range(3):
                connection.execute("INSERT INTO questions (question, category, difficulty, ideal_answer, topic) VALUES (?, 'hr', 'easy', 'An answer.', ?)", (f"Database only {index}?", f"topic-{index}"))
        response = self.client.post("/interview/start", data={"category": "hr", "difficulty": "easy", "question_count": 3})
        self.assertIn(b"Database only", self.client.get(response.location).data)
        with database.get_connection() as connection:
            # Persisted sequences protect questions already assigned to interviews.
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM questions WHERE id = ?", (self.state()["question_ids"][0],))

    def test_schema_initialization_is_repeatable_and_indexed(self):
        database.init_db()
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            plan = connection.execute("EXPLAIN QUERY PLAN SELECT * FROM answers WHERE session_id = 1").fetchall()
            self.assertIn("answers_session_position", str([tuple(row) for row in plan]))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 419)

    def test_parallel_initialization_seeds_once(self):
        with database.get_connection() as connection:
            connection.execute("DELETE FROM questions")
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda unused: database.init_db(), range(4)))
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 419)

    def test_migration_preserves_legacy_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, "DATABASE_PATH", os.path.join(directory, "legacy.db")):
                with closing(sqlite3.connect(database.DATABASE_PATH)) as connection:
                    connection.executescript("""
                        CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, password_hash TEXT);
                        CREATE TABLE questions (id INTEGER PRIMARY KEY, question TEXT, category TEXT, difficulty TEXT, ideal_answer TEXT);
                        CREATE TABLE interview_sessions (id INTEGER PRIMARY KEY, user_id INTEGER, category TEXT, difficulty TEXT, total_questions INTEGER, completed_at TEXT);
                        CREATE TABLE answers (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER, user_answer TEXT, score REAL, performance_level TEXT, suggestion TEXT);
                        INSERT INTO users VALUES (1, 'Legacy', 'old@example.com', 'hash');
                        INSERT INTO questions VALUES (1, 'Old question?', 'hr', 'easy', 'Old ideal');
                        INSERT INTO interview_sessions VALUES (1, 1, 'hr', 'easy', 3, NULL);
                        INSERT INTO answers VALUES (1, 1, 1, 'Old answer', 75, 'Good', 'More detail');
                    """)
                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(lambda unused: database.init_db(), range(4)))
                with database.get_connection() as connection:
                    row = connection.execute("SELECT * FROM answers").fetchone()
                    self.assertEqual(row["user_answer"], "Old answer")
                    self.assertIsNone(row["question_position"])
                    self.assertEqual(row["evaluation_method"], "legacy")
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_frontend_routes_and_static_assets(self):
        for path in ("/", "/login", "/register", "/interview/setup", "/static/css/style.css", "/static/js/script.js"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("app;dur=", response.headers["Server-Timing"])
        self.assertEqual(self.client.get("/missing").status_code, 404)
        self.assertEqual(self.client.get("/interview/submit").status_code, 405)

    def test_real_fallback_submission_latency(self):
        durations = []
        _start_session(self.client, 10)
        for unused in range(10):
            data = self.answer_data()
            started = time.perf_counter()
            response = self.client.post("/interview/submit", data=data, follow_redirects=True)
            durations.append(time.perf_counter() - started)
            self.assertEqual(response.status_code, 200)
        print(f"\nSubmit + next page (real TF-IDF): median={statistics.median(durations)*1000:.1f}ms max={max(durations)*1000:.1f}ms", flush=True)
        self.assertLess(statistics.median(durations), 1.0)


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        from models import answer_evaluator

        self.evaluator = answer_evaluator
        self.environment = patch.dict(os.environ, {"INTERVIEW_SCORING": "semantic"})
        self.environment.start()
        self.loading_patch = patch.object(self.evaluator, "_loading_started", True)
        self.loading_patch.start()
        self.model_patch = patch.object(self.evaluator, "_model", None)
        self.model_patch.start()
        self.evaluator._ideal_embedding.cache_clear()

    def tearDown(self):
        self.evaluator._ideal_embedding.cache_clear()
        self.model_patch.stop()
        self.loading_patch.stop()
        self.environment.stop()

    def test_tfidf_mode_ignores_an_already_loaded_model(self):
        model = Mock()
        self.evaluator._model = model
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf"}):
            self.assertEqual(self.evaluator.evaluate_answer("Python code", "Python language")["method"], "tfidf-fallback")
        model.encode.assert_not_called()

    def test_empty_punctuation_stopwords_and_unicode(self):
        for answer, ideal in (("", "answer"), ("!!!", "???"), ("the and", "or the"), ("日本語", "日本語"), ("a", "I"), ("something", "")):
            result = self.evaluator.evaluate_answer(answer, ideal)
            self.assertTrue(0 <= result["score"] <= 100)
        self.assertEqual(self.evaluator.evaluate_answer("", "answer")["score"], 0)
        self.assertEqual(self.evaluator.evaluate_answer("Python programming language", "Python programming language")["score"], 100)

    def test_pending_or_unavailable_model_does_not_wait(self):
        with patch.object(self.evaluator, "_loading_started", True), patch.dict(os.environ, {"INTERVIEW_SCORING": "semantic"}):
            self.assertEqual(self.evaluator.evaluate_answer("Python code", "Python language")["method"], "tfidf-fallback")

    def test_model_load_is_started_only_once(self):
        with patch.dict(os.environ, {"INTERVIEW_SCORING": "semantic"}), patch.object(self.evaluator, "_loading_started", False), patch.object(self.evaluator, "Thread") as thread:
            for unused in range(3):
                self.evaluator.start_model_loading()
            self.assertEqual(thread.call_count, 1)
            thread.return_value.start.assert_called_once()

    def test_model_load_is_local_only_and_warmed_once(self):
        model = Mock()
        constructor = Mock(return_value=model)
        with patch.dict("sys.modules", {"torch": SimpleNamespace(set_num_threads=Mock()), "sentence_transformers": SimpleNamespace(SentenceTransformer=constructor)}):
            self.evaluator._load_model()
        constructor.assert_called_once_with("all-MiniLM-L6-v2", local_files_only=True)
        model.encode.assert_called_once_with("Model warmup", show_progress_bar=False)
        self.assertIs(self.evaluator._model, model)

    def test_model_failure_is_logged_and_falls_back(self):
        with patch.dict("sys.modules", {"torch": SimpleNamespace(set_num_threads=Mock()), "sentence_transformers": SimpleNamespace(SentenceTransformer=Mock(side_effect=RuntimeError("missing model")))}), self.assertLogs(self.evaluator.logger, level="WARNING"):
            self.evaluator._load_model()
        self.assertIsNone(self.evaluator._model)
        self.assertEqual(self.evaluator.evaluate_answer("Python code", "Python language")["method"], "tfidf-fallback")

    def test_semantic_model_and_ideal_embedding_are_reused(self):
        model = Mock()
        model.encode.return_value = [1.0, 0.0]
        self.evaluator._model = model
        for unused in range(3):
            self.assertEqual(self.evaluator.evaluate_answer("answer", "ideal")["method"], "sentence-transformers")
        self.assertEqual(model.encode.call_count, 4)

    def test_busy_or_failed_inference_falls_back(self):
        self.evaluator._model = Mock()
        self.evaluator._inference_lock.acquire()
        try:
            self.assertEqual(self.evaluator.evaluate_answer("Python code", "Python language")["method"], "tfidf-fallback")
        finally:
            self.evaluator._inference_lock.release()
        self.evaluator._model.encode.side_effect = RuntimeError("inference failure")
        with self.assertLogs(self.evaluator.logger, level="WARNING"):
            self.assertEqual(self.evaluator.evaluate_answer("Python code", "Python language")["method"], "tfidf-fallback")
        self.assertFalse(self.evaluator._inference_lock.locked())


if __name__ == "__main__":
    unittest.main(verbosity=2)
