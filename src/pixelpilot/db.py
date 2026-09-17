from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    seed INTEGER,
    instance_id INTEGER,
    prompt_id TEXT,
    status TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(generations)")}
            if "updated_at" not in columns:
                conn.execute("ALTER TABLE generations ADD COLUMN updated_at TEXT")
                conn.execute("UPDATE generations SET updated_at=created_at WHERE updated_at IS NULL")

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _set_sync(self, key: str, value: Any) -> None:
        now = datetime.now(UTC).isoformat()
        encoded = json.dumps(value, ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, encoded, now),
            )

    async def set(self, key: str, value: Any) -> None:
        await asyncio.to_thread(self._set_sync, key, value)

    def _set_many_sync(self, values: dict[str, Any]) -> None:
        if not values:
            return
        now = datetime.now(UTC).isoformat()
        rows = [
            (key, json.dumps(value, ensure_ascii=False), now)
            for key, value in values.items()
        ]
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                rows,
            )

    async def set_many(self, values: dict[str, Any]) -> None:
        await asyncio.to_thread(self._set_many_sync, values)

    def _get_sync(self, key: str, default: Any = None) -> Any:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return default if row is None else json.loads(row["value"])

    async def get(self, key: str, default: Any = None) -> Any:
        return await asyncio.to_thread(self._get_sync, key, default)

    def _get_many_sync(self, keys: Iterable[str]) -> dict[str, Any]:
        items = list(dict.fromkeys(keys))
        if not items:
            return {}
        placeholders = ",".join("?" for _ in items)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT key,value FROM kv WHERE key IN ({placeholders})",
                items,
            ).fetchall()
        return {str(row["key"]): json.loads(row["value"]) for row in rows}

    async def get_many(self, keys: Iterable[str]) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_many_sync, list(keys))

    def _event_sync(self, kind: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)",
                (kind, json.dumps(payload, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )

    async def event(self, kind: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._event_sync, kind, payload)

    def _create_generation_sync(
        self,
        *,
        prompt: str,
        seed: int,
        instance_id: int,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO generations(prompt,seed,instance_id,prompt_id,status,result_json,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (
                    prompt,
                    seed,
                    instance_id,
                    None,
                    status,
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    now,
                    now,
                ),
            )
            return int(cur.lastrowid)

    async def create_generation(
        self,
        *,
        prompt: str,
        seed: int,
        instance_id: int,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> int:
        return await asyncio.to_thread(
            self._create_generation_sync,
            prompt=prompt,
            seed=seed,
            instance_id=instance_id,
            status=status,
            result=result,
        )

    def _update_generation_sync(
        self,
        generation_id: int,
        *,
        status: str | None = None,
        prompt_id: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        fields: list[str] = ["updated_at=?"]
        values: list[Any] = [datetime.now(UTC).isoformat()]
        if status is not None:
            fields.append("status=?")
            values.append(status)
        if prompt_id is not None:
            fields.append("prompt_id=?")
            values.append(prompt_id)
        if result is not None:
            fields.append("result_json=?")
            values.append(json.dumps(result, ensure_ascii=False))
        values.append(generation_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE generations SET {', '.join(fields)} WHERE id=?", values)

    async def update_generation(
        self,
        generation_id: int,
        *,
        status: str | None = None,
        prompt_id: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._update_generation_sync,
            generation_id,
            status=status,
            prompt_id=prompt_id,
            result=result,
        )

    def _get_generation_sync(self, generation_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM generations WHERE id=?", (generation_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
        return item

    async def get_generation(self, generation_id: int) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_generation_sync, generation_id)

    def _list_generations_sync(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM generations ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
            result.append(item)
        return result

    async def list_generations(self, limit: int = 10) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_generations_sync, limit)
