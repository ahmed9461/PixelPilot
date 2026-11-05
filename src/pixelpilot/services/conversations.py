"""Private SQLite conversations and user-authored instructions.

All writes use transactions and revision checks. Drafts live in Telegram FSM,
never in these tables. No default personality or system instruction is added.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pixelpilot.db import Database


SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_prompts (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
 body TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1,
 previous_json TEXT, revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS chat_personas (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, name TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
 traits_json TEXT NOT NULL DEFAULT '{}',
 prompt_id INTEGER REFERENCES chat_prompts(id) ON DELETE SET NULL,
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS chat_conversations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, title TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 persona_id INTEGER REFERENCES chat_personas(id) ON DELETE SET NULL,
 prompt_id INTEGER REFERENCES chat_prompts(id) ON DELETE SET NULL,
 traits_json TEXT NOT NULL DEFAULT '{}', custom TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS chat_conversations_owner ON chat_conversations(owner_id,updated_at DESC,id DESC);
CREATE TABLE IF NOT EXISTS chat_messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_messages_conversation ON chat_messages(conversation_id,id DESC);
CREATE TABLE IF NOT EXISTS chat_owners (
 owner_id INTEGER PRIMARY KEY,
 active_id INTEGER REFERENCES chat_conversations(id) ON DELETE SET NULL,
 default_persona_id INTEGER REFERENCES chat_personas(id) ON DELETE SET NULL,
 migrated INTEGER NOT NULL DEFAULT 0
);
"""

# These are explicit UI choices, always shown in the effective preview. Empty
# settings produce no system message. Never infer a trait from conversation text.
TRAITS = {
    "formality": ("الرسمية", {"formal": "استخدم أسلوبًا رسميًا.", "casual": "استخدم أسلوبًا عفويًا."}),
    "warmth": ("الود", {"warm": "استخدم أسلوبًا ودودًا.", "neutral": "استخدم أسلوبًا محايدًا."}),
    "humor": ("الفكاهة", {"yes": "استخدم الفكاهة حين تناسب السياق.", "no": "تجنب الفكاهة."}),
    "length": ("طول الرد", {"brief": "أجب بإيجاز.", "detailed": "أجب بتفصيل."}),
    "language": ("لغة الرد", {"ar": "أجب باللغة العربية.", "en": "Reply in English."}),
}
LABELS = {"formal": "رسمي", "casual": "عفوي", "warm": "ودود", "neutral": "محايد",
          "yes": "مفعّلة", "no": "معطّلة", "brief": "موجز", "detailed": "مفصّل", "ar": "العربية", "en": "English"}


class ConversationError(ValueError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat()


def compose_instructions(persona: dict | None, conversation: dict, prompts: list[dict]) -> str:
    """Order: persona body, effective traits, custom text, linked prompt bodies.

    Conversation traits override the same persona trait; identical instructions
    and a prompt linked twice are sent once. Names/descriptions are metadata.
    """
    traits = json.loads(persona["traits_json"]) if persona else {}
    traits.update(json.loads(conversation["traits_json"]))
    parts = [persona["body"] if persona else ""]
    parts += [options[traits[key]] for key, (_, options) in TRAITS.items() if traits.get(key) in options]
    parts += [conversation["custom"]]
    parts += [p["body"] for p in prompts if p["enabled"]]
    return "\n\n".join(dict.fromkeys(p.strip() for p in parts if p.strip()))


class ConversationStore:
    TABLES = {"conversation": "chat_conversations", "persona": "chat_personas", "prompt": "chat_prompts"}

    def __init__(self, db: Database, owner_id: int):
        self.db, self.owner_id = db, owner_id

    def _row(self, conn, kind, item_id):
        row = conn.execute(f"SELECT * FROM {self.TABLES[kind]} WHERE id=? AND owner_id=?", (item_id, self.owner_id)).fetchone()
        if row is None:
            raise ConversationError("العنصر غير موجود أو لا تملك صلاحية الوصول إليه.")
        return dict(row)

    def _new_conversation(self, conn, title="محادثة جديدة"):
        owner = conn.execute("SELECT * FROM chat_owners WHERE owner_id=?", (self.owner_id,)).fetchone()
        stamp = now()
        cur = conn.execute("INSERT INTO chat_conversations(owner_id,title,created_at,updated_at,persona_id) VALUES(?,?,?,?,?)",
                           (self.owner_id, title, stamp, stamp, owner["default_persona_id"]))
        item_id = cur.lastrowid
        conn.execute("UPDATE chat_owners SET active_id=? WHERE owner_id=?", (item_id, self.owner_id))
        return self._row(conn, "conversation", item_id)

    def _owner(self, conn):
        conn.execute("INSERT OR IGNORE INTO chat_owners(owner_id) VALUES(?)", (self.owner_id,))
        owner = conn.execute("SELECT * FROM chat_owners WHERE owner_id=?", (self.owner_id,)).fetchone()
        if not owner["migrated"]:
            # Keep original KV entries intact as a recovery source. Marking and
            # copying happen in one transaction, so restart never duplicates it.
            legacy = conn.execute("SELECT value,updated_at FROM kv WHERE key=?", (f"chat.history.{self.owner_id}",)).fetchone()
            if legacy is None:
                legacy = conn.execute("SELECT value,updated_at FROM kv WHERE key='chat.history'").fetchone()
                # Unscoped legacy belongs only to the configured owner, which
                # main initializes first. Never copy it into a second owner.
                if conn.execute("SELECT 1 FROM chat_owners WHERE migrated=1").fetchone():
                    legacy = None
            turns = json.loads(legacy["value"]) if legacy else []
            valid = [t for t in turns if isinstance(t, dict) and t.get("role") in {"user", "assistant"}
                     and isinstance(t.get("content"), str)] if isinstance(turns, list) else []
            if valid:
                item = self._new_conversation(conn, "المحادثة السابقة")
                conn.executemany("INSERT INTO chat_messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                                 [(item["id"], t["role"], t["content"], legacy["updated_at"]) for t in valid])
                conn.execute("UPDATE chat_conversations SET updated_at=? WHERE id=?", (legacy["updated_at"], item["id"]))
            conn.execute("UPDATE chat_owners SET migrated=1 WHERE owner_id=?", (self.owner_id,))

    def _run(self, operation, *args):
        with self.db._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._owner(conn)
            return operation(conn, *args)

    async def _call(self, operation, *args):
        return await asyncio.to_thread(self._run, operation, *args)

    async def init(self):
        await self._call(lambda conn: None)

    def _active(self, conn):
        item_id = conn.execute("SELECT active_id FROM chat_owners WHERE owner_id=?", (self.owner_id,)).fetchone()[0]
        return self._row(conn, "conversation", item_id) if item_id else self._new_conversation(conn)

    async def active(self):
        return await self._call(self._active)

    async def get(self, kind, item_id):
        return await self._call(self._row, kind, item_id)

    async def listing(self, kind, page=0, size=6):
        def query(conn):
            table = self.TABLES[kind]
            count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE owner_id=?", (self.owner_id,)).fetchone()[0]
            order = "updated_at DESC,id DESC" if kind == "conversation" else "id DESC"
            page_num = min(max(0, page), max(0, (count-1)//size))
            rows = conn.execute(f"SELECT * FROM {table} WHERE owner_id=? ORDER BY {order} LIMIT ? OFFSET ?",
                                (self.owner_id, size, page_num*size)).fetchall()
            return [dict(r) for r in rows], count, page_num
        return await self._call(query)

    async def create(self, kind, values):
        def create(conn):
            clean = self._validate(kind, values)
            if kind == "conversation":
                return self._new_conversation(conn, clean.get("title", "محادثة جديدة"))
            if clean.get("prompt_id") is not None:
                self._row(conn,"prompt",clean["prompt_id"])
            fields = ["owner_id", *clean]
            cur = conn.execute(f"INSERT INTO {self.TABLES[kind]}({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
                               [self.owner_id, *clean.values()])
            return self._row(conn, kind, cur.lastrowid)
        return await self._call(create)

    def _validate(self, kind, values):
        allowed = {"conversation": {"title", "persona_id", "prompt_id", "traits_json", "custom"},
                   "persona": {"name", "description", "body", "traits_json", "prompt_id"},
                   "prompt": {"name", "body", "enabled"}}[kind]
        if not values or not set(values) <= allowed:
            raise ConversationError("حقول غير صالحة.")
        clean = dict(values)
        for key, value in clean.items():
            if key in {"title", "name", "description", "body", "custom"}:
                limit = 80 if key in {"title", "name"} else (500 if key == "description" else 6000)
                if not isinstance(value, str) or len(value) > limit or (key in {"title", "name"} and not value.strip()):
                    raise ConversationError(f"قيمة غير صالحة؛ الحد {limit} حرف.")
                clean[key] = value.strip()
            elif key == "traits_json":
                traits = json.loads(value)
                if not isinstance(traits, dict) or any(k not in TRAITS or v not in TRAITS[k][1] for k,v in traits.items()):
                    raise ConversationError("سمات غير صالحة.")
            elif key == "enabled" and value not in (0, 1):
                raise ConversationError("حالة غير صالحة.")
        return clean

    async def update(self, kind, item_id, revision, values):
        def update(conn):
            old = self._row(conn, kind, item_id)
            self._check(old, revision)
            clean = self._validate(kind, values)
            for field, target in (("persona_id", "persona"), ("prompt_id", "prompt")):
                if clean.get(field) is not None:
                    self._row(conn, target, clean[field])
            if kind == "prompt":
                clean["previous_json"] = json.dumps({k: old[k] for k in ("name", "body", "enabled")}, ensure_ascii=False)
            conn.execute(f"UPDATE {self.TABLES[kind]} SET {','.join(k+'=?' for k in clean)}, revision=revision+1 WHERE id=?",
                         [*clean.values(), item_id])
            return self._row(conn, kind, item_id)
        return await self._call(update)

    @staticmethod
    def _check(row, revision):
        if row["revision"] != revision:
            raise ConversationError("تغيّر العنصر أثناء التحرير. أعد فتحه لتجنب استبدال تعديل أحدث.")

    async def restore(self, item_id, revision):
        row = await self.get("prompt", item_id)
        if not row["previous_json"]:
            raise ConversationError("لا توجد نسخة سابقة.")
        return await self.update("prompt", item_id, revision, json.loads(row["previous_json"]))

    async def copy_persona(self, item_id):
        row = await self.get("persona", item_id)
        return await self.create("persona", {k: (row[k][:70]+" (نسخة)" if k == "name" else row[k])
                                             for k in ("name", "description", "body", "traits_json", "prompt_id")})

    async def delete(self, kind, item_id, revision):
        def delete(conn):
            self._check(self._row(conn, kind, item_id), revision)
            conn.execute(f"DELETE FROM {self.TABLES[kind]} WHERE id=? AND owner_id=?", (item_id, self.owner_id))
        await self._call(delete)

    async def select(self, item_id):
        def select(conn):
            row = self._row(conn, "conversation", item_id)
            conn.execute("UPDATE chat_owners SET active_id=? WHERE owner_id=?", (item_id, self.owner_id))
            return row
        return await self._call(select)

    async def default_persona(self, item_id=None, *, set_value=False):
        def default(conn):
            if set_value:
                if item_id is not None:
                    self._row(conn, "persona", item_id)
                conn.execute("UPDATE chat_owners SET default_persona_id=? WHERE owner_id=?", (item_id, self.owner_id))
            return conn.execute("SELECT default_persona_id FROM chat_owners WHERE owner_id=?", (self.owner_id,)).fetchone()[0]
        return await self._call(default)

    async def messages(self, item_id, page=0, size=4):
        def query(conn):
            self._row(conn, "conversation", item_id)
            count = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE conversation_id=?", (item_id,)).fetchone()[0]
            page_num = min(max(0,page), max(0,(count-1)//size))
            rows = conn.execute("SELECT * FROM chat_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                                (item_id,size,page_num*size)).fetchall()
            return [dict(r) for r in reversed(rows)], count, page_num
        return await self._call(query)

    def _context(self, conn, item_id, turns):
        conversation = self._row(conn, "conversation", item_id)
        persona = self._row(conn, "persona", conversation["persona_id"]) if conversation["persona_id"] else None
        ids = list(dict.fromkeys([x for x in [persona["prompt_id"] if persona else None, conversation["prompt_id"]] if x]))
        prompts = [self._row(conn, "prompt", i) for i in ids]
        rows = conn.execute("SELECT role,content FROM chat_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                            (item_id, turns*2)).fetchall()
        return {"conversation": conversation, "persona": persona, "prompts": prompts,
                "system": compose_instructions(persona, conversation, prompts),
                "history": [dict(r) for r in reversed(rows)]}

    async def context(self, item_id, turns=8):
        return await self._call(self._context, item_id, turns)

    async def append(self, item_id, user, assistant):
        def append(conn):
            conversation = self._row(conn, "conversation", item_id)
            stamp = now()
            conn.executemany("INSERT INTO chat_messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",
                             [(item_id, "user", user, stamp), (item_id, "assistant", assistant, stamp)])
            title = user.replace("\n", " ")[:60] if conversation["title"] == "محادثة جديدة" else conversation["title"]
            conn.execute("UPDATE chat_conversations SET updated_at=?,title=?,revision=revision+1 WHERE id=?", (stamp,title,item_id))
        await self._call(append)

    async def clear(self, item_id):
        def clear(conn):
            self._row(conn, "conversation", item_id)
            conn.execute("DELETE FROM chat_messages WHERE conversation_id=?", (item_id,))
            conn.execute("UPDATE chat_conversations SET updated_at=?,revision=revision+1 WHERE id=?", (now(),item_id))
        await self._call(clear)
