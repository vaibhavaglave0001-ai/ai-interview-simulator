"""Small compatibility layer retaining the application's existing SQLite SQL."""

import os
import sqlite3
from contextlib import contextmanager

from libsql_client import LibsqlError, create_client_sync


def translate_error(error):
    if str(error.code).startswith("SQLITE_CONSTRAINT"):
        return sqlite3.IntegrityError("Database constraint failed")
    return sqlite3.OperationalError("Hosted database request failed")


class RemoteConnection:
    def __init__(self, client):
        self.transaction = client.transaction()

    def execute(self, sql, parameters=()):
        try:
            return RemoteCursor(self.transaction.execute(sql, parameters))
        except LibsqlError as error:
            raise translate_error(error) from None

    def executemany(self, sql, rows):
        for parameters in rows:
            self.execute(sql, parameters)


class RemoteCursor:
    def __init__(self, result):
        self.rows = iter(result.rows)
        self.lastrowid = result.last_insert_rowid

    def fetchone(self):
        return next(self.rows, None)

    def __iter__(self):
        return self.rows

    def fetchall(self):
        return list(self.rows)


def create_remote_client():
    url = os.environ["TURSO_DATABASE_URL"]
    token = os.environ.get("TURSO_AUTH_TOKEN")
    # TLS WebSockets preserve transactions across statements; HTTP does not.
    if not url.startswith(("libsql://", "wss://")) or "?" in url:
        raise RuntimeError("Use a TLS libsql:// database URL without query parameters")
    if not token:
        raise RuntimeError("TURSO_AUTH_TOKEN is required")
    return create_client_sync(url=url, auth_token=token)


@contextmanager
def remote_connection():
    client = None
    connection = None
    try:
        client = create_remote_client()
        client.execute("PRAGMA foreign_keys = ON")
        connection = RemoteConnection(client)
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise sqlite3.OperationalError("Hosted database must enable foreign keys")
        yield connection
        connection.transaction.commit()
    except LibsqlError as error:
        raise translate_error(error) from None
    finally:
        if connection is not None:
            connection.transaction.close()
        if client is not None:
            client.close()
