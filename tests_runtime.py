"""Exercise a real HTTP server and real scoring against a disposable database."""

import http.cookiejar
import os
import statistics
import tempfile
import time
from html.parser import HTMLParser
from threading import Thread
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener
from unittest.mock import patch

from werkzeug.serving import make_server

import database


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.links = []
        self.forms = {}

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name"):
            self.fields[attributes["name"]] = attributes.get("value", "")
        if tag == "a":
            self.links.append(attributes.get("href"))
        if tag == "form" and attributes.get("id"):
            self.forms[attributes["id"]] = attributes


def run():
    with tempfile.TemporaryDirectory() as directory, patch.object(database, "DATABASE_PATH", os.path.join(directory, "runtime.db")):
        import app as interview_app
        from models import answer_evaluator

        server = make_server("127.0.0.1", 0, interview_app.app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f"http://127.0.0.1:{server.server_port}"
        client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        fields = {}

        def request(path, data=None):
            nonlocal fields
            payload = None if data is None else urlencode({"csrf_token": fields.get("csrf_token", ""), **data}).encode()
            with client.open(origin + path, data=payload, timeout=30) as response:
                assert response.status == 200
                html = response.read().decode()
                parser = FormParser()
                parser.feed(html)
                fields = {"csrf_token": fields.get("csrf_token", ""), **parser.fields}
                return html

        def complete_interview(label):
            dashboard = FormParser()
            dashboard.feed(request("/"))
            assert "/interview/setup" in dashboard.links
            assert "setup-form" not in dashboard.forms
            setup = FormParser()
            setup.feed(request("/interview/setup"))
            assert setup.forms["setup-form"]["action"] == "/interview/start"
            html = request(setup.forms["setup-form"]["action"], {"category": "technical", "difficulty": "easy", "question_count": 3})
            durations = []
            for position in range(3):
                assert f"Question {position + 1} of 3" in html
                started = time.perf_counter()
                html = request("/interview/submit", {**fields, "answer": "Python is an interpreted programming language with readable syntax. An API allows software to communicate through requests and responses. A variable refers to a value."})
                durations.append((time.perf_counter() - started) * 1000)
            assert "SESSION COMPLETE" in html
            assert html.count('class="answer-review"') == 3
            print(f"{label} real HTTP submit + next page: median={statistics.median(durations):.1f}ms max={max(durations):.1f}ms", flush=True)

        try:
            request("/register")
            request("/register", {"name": "Runtime Test", "email": "runtime@example.com", "password": "test-password"})
            dashboard_html = request("/login", {"email": "runtime@example.com", "password": "test-password"})
            assert "Start an interview" in dashboard_html
            assert 'id="setup-form"' not in dashboard_html
            complete_interview("During model startup")
            deadline = time.monotonic() + 90
            while answer_evaluator._model is None and time.monotonic() < deadline:
                time.sleep(0.1)
            assert answer_evaluator._model is not None, "Cached semantic model was not available within 90 seconds"
            complete_interview("With cached semantic model")
            with database.get_connection() as connection:
                methods = dict(connection.execute("SELECT evaluation_method, COUNT(*) FROM answers GROUP BY evaluation_method").fetchall())
                assert methods.get("sentence-transformers", 0) >= 3
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert not connection.execute("PRAGMA foreign_key_check").fetchall()
                print(f"Persisted scoring methods: {methods}", flush=True)
            request("/logout", {})
            assert "Log in" in request("/interview/setup")
            print("Real HTTP registration -> login -> interviews -> results -> logout passed.", flush=True)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    run()
