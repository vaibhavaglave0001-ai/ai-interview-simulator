"""Copy a consistent, migrated local snapshot to an EMPTY hosted libSQL DB.

Requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN in the shell environment.
No local rows are deleted or modified. Existing hosted databases are refused.
"""

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import database
from remote_database import create_remote_client
from scripts.deployment_config import load_settings


def main():
    client = create_remote_client()
    try:
        if client.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").rows:
            raise RuntimeError("Hosted database is not empty; refusing to overwrite it")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "migration.db"
            source = sqlite3.connect(f"{database.DATABASE_PATH.as_uri()}?mode=ro", uri=True)
            target = sqlite3.connect(path)
            try:
                source.backup(target)
            finally:
                source.close()
                target.close()
            with patch.dict(os.environ), patch.object(database, "DATABASE_PATH", path):
                os.environ.pop("TURSO_DATABASE_URL", None)
                os.environ.pop("VERCEL", None)
                database.init_db()
            snapshot = sqlite3.connect(path)
            try:
                statements = [sql for sql in snapshot.iterdump() if sql not in ("BEGIN TRANSACTION;", "COMMIT;")]
                counts = {name: snapshot.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                          for name in ("users", "questions", "interview_sessions", "session_questions", "answers")}
            finally:
                snapshot.close()
            # One atomic batch preserves IDs, relationships, users, and prior results.
            statements = [sql for sql in statements if sql not in ("BEGIN TRANSACTION;", "COMMIT;")]
            client.batch(["PRAGMA defer_foreign_keys = ON", *statements])
            if client.execute("PRAGMA foreign_key_check").rows:
                raise RuntimeError("Hosted foreign-key verification failed")
            for name, count in counts.items():
                assert client.execute(f'SELECT COUNT(*) FROM "{name}"').rows[0][0] == count
            print("Migration verified. Row counts:", counts)
    finally:
        client.close()


if __name__ == "__main__":
    load_settings()
    main()
