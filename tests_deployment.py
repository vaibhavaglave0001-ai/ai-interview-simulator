"""Exercise deployment changes with the real libSQL SDK and a disposable DB."""

import importlib
from contextlib import closing
import os
import runpy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import database
from libsql_client import create_client_sync
from libsql_client.sqlite3_utils import Sqlite3Client
from tests_smoke import FormClient, _start_session, _complete_session


class DeploymentTests(unittest.TestCase):
    def test_production_requires_secret_and_secure_cookies(self):
        settings = {"VERCEL": "1", "SECRET_KEY": "", "INTERVIEW_SCORING": "tfidf"}
        with patch.dict(os.environ, settings):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                runpy.run_path(str(Path(__file__).with_name("app.py")))
            os.environ["SECRET_KEY"] = "test-only-production-key-" * 3
            with patch.object(database, "init_db"):
                namespace = runpy.run_path(str(Path(__file__).with_name("app.py")))
            application = namespace["app"]
            self.assertTrue(application.config["SESSION_COOKIE_SECURE"])
            response = application.test_client().get("/login")
            cookie = response.headers["Set-Cookie"]
            self.assertIn("Secure", cookie)
            self.assertIn("HttpOnly", cookie)
            self.assertIn("SameSite=Lax", cookie)
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_database_failure_does_not_expose_details(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, "DATABASE_PATH", Path(directory) / "error.db"), patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf", "TURSO_DATABASE_URL": ""}):
                database.init_db()
                module = importlib.import_module("app")
                module.app.config.update(TESTING=True)
                client = module.app.test_client()
                client.get("/login")
                with client.session_transaction() as state:
                    token = state["csrf_token"]
                with patch.object(module, "get_connection", side_effect=sqlite3.OperationalError("private-database-detail")):
                    response = client.post("/login", data={"csrf_token": token, "email": "test@example.com", "password": "test"})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(b"private-database-detail", response.data)

    def test_hosted_adapter_authentication_flow_and_atomic_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "remote.db"
            with patch.object(database, "DATABASE_PATH", path), patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf", "TURSO_DATABASE_URL": ""}):
                database.init_db()
                module = importlib.import_module("app")
            original_connect = Sqlite3Client._connect

            def connect(client):
                connection = original_connect(client)
                connection.execute("PRAGMA foreign_keys = ON")
                return connection

            with patch.dict(os.environ, {"INTERVIEW_SCORING": "tfidf", "TURSO_DATABASE_URL": "libsql://test.invalid"}), patch("remote_database.create_remote_client", side_effect=lambda: create_client_sync(path.as_uri())), patch.object(Sqlite3Client, "_connect", connect):
                database.init_db()
                module.app.config.update(TESTING=True, SECRET_KEY="test-only-secret")
                module.app.test_client_class = FormClient
                client = module.app.test_client()
                fields = {"name": "Remote Test", "email": "remote@example.com", "password": "test-password"}
                self.assertEqual(client.post("/register", data=fields).status_code, 302)
                duplicate = client.post("/register", data=fields, follow_redirects=True)
                self.assertIn(b"already exists", duplicate.data)
                self.assertEqual(client.post("/login", data=fields).status_code, 302)
                for count in (3, 5, 10):
                    interview_id = _start_session(client, count)
                    _complete_session(client, interview_id, count)
                with self.assertRaises(sqlite3.IntegrityError), database.get_connection() as connection:
                    connection.execute("INSERT INTO users(name,email,password_hash) VALUES('Rollback','rollback@example.com','test')")
                    connection.execute("INSERT INTO users(name,email,password_hash) VALUES('Duplicate','remote@example.com','test')")
                with database.get_connection() as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0], 18)
                    self.assertFalse(connection.execute("PRAGMA foreign_key_check").fetchall())
                self.assertEqual(client.post("/logout").status_code, 302)

    def test_snapshot_migration_preserves_source_and_refuses_existing_target(self):
        from scripts import setup_database
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.db"
            destination = Path(directory) / "destination.db"
            with patch.object(database, "DATABASE_PATH", source), patch.dict(os.environ, {"TURSO_DATABASE_URL": ""}):
                database.init_db()
                with database.get_connection() as connection:
                    connection.execute("INSERT INTO users(id,name,email,password_hash) VALUES(17,'Migration','migrate@example.com','test')")
                original = source.read_bytes()
                with patch.object(setup_database, "create_remote_client", side_effect=lambda: create_client_sync(destination.as_uri())):
                    setup_database.main()
                    with self.assertRaisesRegex(RuntimeError, "not empty"):
                        setup_database.main()
                self.assertEqual(original, source.read_bytes())
                with closing(sqlite3.connect(destination)) as connection:
                    self.assertEqual(connection.execute("SELECT id FROM users").fetchone()[0], 17)

    def test_onnx_embeddings_are_normalized_and_semantic(self):
        import numpy as np
        from models.onnx_encoder import MiniLMEncoder
        encoder = MiniLMEncoder()
        first = encoder.encode("A person writes computer software.")
        related = encoder.encode("Someone is programming an application.")
        unrelated = encoder.encode("The tropical fruit tastes sweet.")
        self.assertEqual(first.shape, (384,))
        self.assertAlmostEqual(float(np.linalg.norm(first)), 1.0, places=5)
        self.assertGreater(float(first @ related), float(first @ unrelated) + 0.2)
        self.assertTrue(np.isfinite(encoder.encode("" )).all())
        self.assertTrue(np.isfinite(encoder.encode("long answer " * 1000)).all())


if __name__ == "__main__":
    unittest.main(verbosity=2)
