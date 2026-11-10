"""개인 PC용 대화 저장소. API 키와 실행 중인 스레드는 저장하지 않는다."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import messages_from_dict, messages_to_dict

# 대화 데이터베이스를 저장할 폴더
DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 대화 데이터베이스 경로
DB_PATH = DATA_DIR / "chat_history.sqlite3"


def new_chat(messages):
    return {"chat_id": uuid4().hex, "title": "새 대화", "revision": 0,
            "messages": messages, "turns": [], "files": [],
            "upload_keys": set(), "uploader_version": 0, "job": None}


def connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.execute("""CREATE TABLE IF NOT EXISTS chats (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL, payload TEXT NOT NULL)""")
    connection.commit()
    return connection


def save_chat(state):
    title = (" ".join(state["turns"][0]["question"].split())[:40]
             if state["turns"] else "새 대화")
    payload = {
        "messages": messages_to_dict(state["messages"]),
        "turns": state["turns"], "files": state["files"],  # turns의 usage도 함께 저장
        "upload_keys": sorted(state["upload_keys"]),
    }
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    revision = state.get("revision", 0)
    updated = datetime.now().astimezone().isoformat(timespec="seconds")
    with closing(connect()) as connection, connection:
        if revision == 0:
            connection.execute("INSERT INTO chats VALUES (?, ?, ?, ?, ?)",
                               (state["chat_id"], title, updated, 1, serialized))
        else:
            cursor = connection.execute(
                "UPDATE chats SET title=?, updated_at=?, revision=?, payload=? "
                "WHERE id=? AND revision=?",
                (title, updated, revision + 1, serialized, state["chat_id"], revision))
            if cursor.rowcount != 1:
                raise RuntimeError("다른 탭에서 이 대화가 변경되었습니다. 현재 내용을 복사한 뒤 앱을 다시 열어주세요.")
    state["revision"] = revision + 1
    state["title"] = title


def list_chats():
    with closing(connect()) as connection:
        return [{"id": row[0], "title": row[1], "updated_at": row[2]}
                for row in connection.execute(
                    "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC, rowid DESC")]


def load_chat(chat_id):
    with closing(connect()) as connection:
        row = connection.execute(
            "SELECT title, revision, payload FROM chats WHERE id=?", (chat_id,)).fetchone()
    if row is None:
        raise ValueError("저장된 대화를 찾을 수 없습니다.")
    data = json.loads(row[2])
    state = new_chat(messages_from_dict(data["messages"]))
    state.update(chat_id=chat_id, title=row[0], revision=row[1],
                 turns=data["turns"], files=data["files"],
                 upload_keys={tuple(item) for item in data["upload_keys"]})
    return state
