from __future__ import annotations

import json
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


class SQLiteStorage:
    """Memoria local para pruebas. En Streamlit Cloud se recomienda Firestore."""

    mode = "local"

    def __init__(self, path: str | Path = "data/copiloto_capex.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                folio TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get_project(self, folio: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM projects WHERE folio = ?", (folio,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_project(self, project: dict[str, Any]) -> None:
        payload = json.dumps(project, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO projects(folio, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(folio) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (project["folio"], payload, project["updated_at"]),
            )
            self._conn.commit()

    def delete_project(self, folio: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM projects WHERE folio = ?", (folio,))
            self._conn.commit()


class FirestoreStorage:
    """Memoria compartida. Las credenciales se reciben desde st.secrets."""

    mode = "firestore"

    def __init__(self, credentials_info: dict[str, Any]) -> None:
        from google.cloud import firestore
        from google.oauth2 import service_account

        info = deepcopy(credentials_info)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        credentials = service_account.Credentials.from_service_account_info(info)
        self._client = firestore.Client(
            project=info["project_id"], credentials=credentials
        )
        self._collection = self._client.collection("expedientes")

    def list_projects(self) -> list[dict[str, Any]]:
        docs = [doc.to_dict() for doc in self._collection.stream()]
        return sorted(docs, key=lambda item: item.get("updated_at", ""), reverse=True)

    def get_project(self, folio: str) -> dict[str, Any] | None:
        snapshot = self._collection.document(folio).get()
        return snapshot.to_dict() if snapshot.exists else None

    def save_project(self, project: dict[str, Any]) -> None:
        self._collection.document(project["folio"]).set(project)

    def delete_project(self, folio: str) -> None:
        self._collection.document(folio).delete()


def build_storage(secrets: Any | None = None):
    """Usa Firestore si hay credenciales completas; de lo contrario SQLite."""
    try:
        firebase = dict(secrets["firebase"]) if secrets and "firebase" in secrets else {}
    except Exception:
        firebase = {}

    required = {"type", "project_id", "private_key", "client_email", "token_uri"}
    if required.issubset(firebase):
        return FirestoreStorage(firebase)
    return SQLiteStorage()
