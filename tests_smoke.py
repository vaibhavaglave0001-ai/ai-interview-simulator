"""Small no-network smoke test for the complete Flask route flow."""

import os
import tempfile

import database
from flask.testing import FlaskClient
from unittest.mock import patch


class FormClient(FlaskClient):
    def post(self, *args, **kwargs):
        with self.session_transaction() as state:
            token = state.get("csrf_token")
        if token is None:
            self.get("/")
            with self.session_transaction() as state:
                token = state["csrf_token"]
        kwargs["data"] = {**kwargs.get("data", {}), "csrf_token": token}
        return super().post(*args, **kwargs)


def _fake_evaluator(user_answer, ideal_answer):
    return {
        "score": 75.0,
        "level": "Good",
        "suggestion": "Keep the answer specific and structured.",
        "method": "test",
    }


def _start_session(client, count):
    response = client.post(
        "/interview/start",
        data={"category": "hr", "difficulty": "easy", "question_count": str(count)},
    )
    assert response.status_code == 302
    with client.session_transaction() as state:
        assert len(state["question_ids"]) == count
        assert state["selected_question_count"] == count
        return state["interview_id"]


def _complete_session(client, interview_id, count):
    early_result = client.get(f"/result/{interview_id}")
    assert early_result.status_code == 302
    assert "/interview/question/" in early_result.headers["Location"]

    for index in range(count):
        with client.session_transaction() as state:
            question_id = state["question_ids"][state["question_index"]]
            position = state["question_index"]
        assert position == index

        response = client.get(f"/interview/question/{question_id}")
        assert response.status_code == 200
        assert f"Question {index + 1} of {count}".encode() in response.data

        response = client.post(
            "/interview/submit",
            data={
                "interview_id": interview_id,
                "question_id": question_id,
                "question_position": position,
                "answer": "I would explain the situation, action, and result clearly.",
            },
        )
        assert response.status_code == 302

    response = client.get(f"/result/{interview_id}")
    assert response.status_code == 200
    assert b"SESSION COMPLETE" in response.data
    assert response.data.count(b'class="answer-review"') == count


def run():
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.object(database, "DATABASE_PATH", os.path.join(temp_dir, "test.db")), patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf"}):
            import app as interview_app

            database.init_db()
            interview_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
            interview_app.app.test_client_class = FormClient
            client = interview_app.app.test_client()
            with patch.object(interview_app, "evaluate_answer", _fake_evaluator):
                response = client.post(
                    "/register",
                    data={"name": "Test User", "email": "test@example.com", "password": "secret1"},
                )
                assert response.status_code == 302
                response = client.post("/login", data={"email": "test@example.com", "password": "secret1"})
                assert response.status_code == 302

                for count in (3, 5, 10):
                    interview_id = _start_session(client, count)
                    _complete_session(client, interview_id, count)

    print("Smoke test passed: exact 3/5/10 question flow -> evaluation -> result")


if __name__ == "__main__":
    run()
