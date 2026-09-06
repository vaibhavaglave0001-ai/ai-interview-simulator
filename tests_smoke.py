"""Small no-network smoke test for the complete Flask route flow."""

import os
import tempfile

import database
from app import app


def run():
    with tempfile.TemporaryDirectory() as temp_dir:
        database.DATABASE_PATH = os.path.join(temp_dir, "test.db")
        database.init_db()
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        client = app.test_client()
        response = client.post("/register", data={"name": "Test User", "email": "test@example.com", "password": "secret1"})
        assert response.status_code == 302
        response = client.post("/login", data={"email": "test@example.com", "password": "secret1"})
        assert response.status_code == 302
        response = client.post("/interview/start", data={"category": "technical", "difficulty": "easy", "question_count": "1"})
        assert response.status_code == 302
        with client.session_transaction() as state:
            question_id = state["question_ids"][0]
            interview_id = state["interview_id"]
        response = client.get(f"/interview/question/{question_id}")
        assert response.status_code == 200
        response = client.post("/interview/submit", data={"question_id": question_id, "answer": "Python is a high-level programming language."})
        assert response.status_code == 302
        response = client.get(f"/result/{interview_id}")
        assert response.status_code == 200
        assert b"SESSION COMPLETE" in response.data
    print("Smoke test passed: register -> login -> interview -> evaluation -> result")


if __name__ == "__main__":
    run()
