# -*- coding: utf-8 -*-
"""Persistent, auditable supply assessment, replenishment and risk artifacts."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupplyWorkflowStore:
    """SQLite repository for supply artifacts and their named reviews."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("SUPPLY_STUDIO_DB")
        self.path = Path(configured) if configured else Path.home() / ".zhiyun-supply-studio" / "supply.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS supply_artifacts (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    payload_json TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS supply_reviews (
                    id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL REFERENCES supply_artifacts(id),
                    action TEXT NOT NULL, reviewer TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL
                );
            """)

    def create_artifact(self, kind: str, title: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind not in {"supplier", "replenishment", "risk"}:
            raise ValueError("供应链工件类型必须是 supplier、replenishment 或 risk")
        artifact_id, now = str(uuid.uuid4()), _now()
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO supply_artifacts VALUES (?,?,?,?,?,?,?)",
                (artifact_id, kind, title, json.dumps(payload, ensure_ascii=False), "pending_review", now, now),
            )
        return self.get_artifact(artifact_id)

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM supply_artifacts WHERE id=?", (artifact_id,)).fetchone()
            if not row:
                raise KeyError(artifact_id)
            reviews = [dict(item) for item in db.execute(
                "SELECT * FROM supply_reviews WHERE artifact_id=? ORDER BY created_at", (artifact_id,)
            )]
            result = dict(row)
            result["payload"] = json.loads(result.pop("payload_json"))
            result["reviews"] = reviews
            return result

    def list_artifacts(self, kind: str | None = None, limit: int = 100) -> dict[str, Any]:
        with closing(self._connect()) as db, db:
            if kind:
                rows = db.execute(
                    "SELECT * FROM supply_artifacts WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                    (kind, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM supply_artifacts ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return {"artifacts": [dict(row) for row in rows], "count": len(rows)}

    def review_artifact(self, artifact_id: str, action: str, reviewer: str, note: str | None = None) -> dict[str, Any]:
        if action not in {"accept", "reject"}:
            raise ValueError("审阅动作必须是 accept 或 reject")
        if not reviewer.strip():
            raise ValueError("审阅人不能为空")
        self.get_artifact(artifact_id)
        now = _now()
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO supply_reviews VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), artifact_id, action, reviewer.strip(), note, now),
            )
            db.execute(
                "UPDATE supply_artifacts SET status=?, updated_at=? WHERE id=?",
                ("accepted" if action == "accept" else "rejected", now, artifact_id),
            )
        return self.get_artifact(artifact_id)

    def export_artifact(self, artifact_id: str) -> tuple[str, str]:
        artifact = self.get_artifact(artifact_id)
        if artifact["status"] != "accepted":
            raise ValueError("只有已接受的供应链工件可以导出")
        return json.dumps(artifact, ensure_ascii=False, indent=2), "application/json"
