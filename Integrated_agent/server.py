"""개인 PC용 Flutter API. 기존 agent/chat_store/file_utils 및 .env를 사용한다."""
import hashlib
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent import ALL_TOOLS, TOOL_LABELS, create_messages, stream_agent
from chat_store import list_chats, load_chat, new_chat, save_chat
from config import (MAX_UPLOAD_MB, UPLOAD_DIR, OUTPUT_DIR, OPENAI_API_KEY,
                    TYPESAFE_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET,
                    OPENAI_MODEL, JEV_MODEL)
from file_utils import ALLOWED_UPLOAD_EXTENSIONS
from usage_tracking import USAGE_SINK, summarize_usage

logger = logging.getLogger("uvicorn.error")
app = FastAPI(title="AI Agent", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False, allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
chat_lock = Lock()
active_chat_id = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=50000)
    chat_id: str | None = None
    force_judgment: bool = False
    continue_case: bool = False


@contextmanager
def locked():
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "다른 요청을 처리하고 있어요. 잠시 후 다시 시도해주세요.")
    try:
        yield
    finally:
        chat_lock.release()


def get_chat(chat_id=None):
    global active_chat_id
    selected = chat_id or active_chat_id
    if selected:
        try:
            return load_chat(selected)
        except ValueError as error:
            raise HTTPException(404, "대화를 찾을 수 없습니다.") from error
    chats = list_chats()
    if chats:
        state = load_chat(chats[0]["id"])
    else:
        state = new_chat(create_messages())
        save_chat(state)
    active_chat_id = state["chat_id"]
    return state


def allowed_path(raw):
    path = Path(raw).resolve()
    if not any(path.is_relative_to(Path(root).resolve()) for root in (UPLOAD_DIR, OUTPUT_DIR)):
        raise ValueError("등록된 파일 폴더 밖의 경로입니다.")
    if not path.is_file():
        raise ValueError("파일이 없습니다.")
    return path


def public_files(state):
    result = []
    for index, item in enumerate(state["files"]):
        try:
            path = allowed_path(item["path"])
            result.append({"name": item["name"], "size": path.stat().st_size,
                           "url": f"/chats/{state['chat_id']}/files/{index}"})
        except (ValueError, OSError, KeyError):
            continue
    return result


def generated_files(state, records):
    paths = set()
    for record in records:
        if record.get("name") not in {"create_report", "transcribe_audio"}:
            continue
        data = record.get("data")
        if not isinstance(data, dict) or not data.get("성공"):
            continue
        candidates = data.get("생성 파일", []) if record["name"] == "transcribe_audio" else [data]
        for item in candidates:
            try:
                path = allowed_path(item["파일 경로"])
                if not path.is_relative_to(Path(OUTPUT_DIR).resolve()):
                    continue
                raw = str(path)
                paths.add(raw)
                if not any(f["path"] == raw for f in state["files"]):
                    state["files"].append({"name": path.name, "path": raw})
            except (KeyError, ValueError, TypeError, OSError):
                continue
    return [f for f in state["files"] if f["path"] in paths]


def public_turn(state, turn):
    result = {k: turn.get(k) for k in ("question", "answer", "results", "error", "usage", "elapsed")}
    wanted = {f.get("path") for f in turn.get("files", [])}
    all_files = public_files(state)
    result["files"] = [f for f in all_files if
                       state["files"][int(f["url"].rsplit('/', 1)[1])]["path"] in wanted]
    return result


def snapshot(state):
    return {"chat_id": state["chat_id"], "title": state["title"],
            "turns": [public_turn(state, t) for t in state["turns"]],
            "files": public_files(state)}


@app.get("/")
def home():
    return {"status": "AI Agent FastAPI Server is running!", "version": "2.0"}


@app.get("/capabilities")
def capabilities():
    return {"tools": [{"name": t.name, "label": TOOL_LABELS.get(t.name, t.name)} for t in ALL_TOOLS],
            "max_upload_mb": MAX_UPLOAD_MB,
            "extensions": sorted(e.lstrip('.') for e in ALLOWED_UPLOAD_EXTENSIONS),
            "providers": [
                {"name": "OpenAI", "model": OPENAI_MODEL, "configured": bool(OPENAI_API_KEY)},
                {"name": "Jev", "model": JEV_MODEL, "configured": bool(TYPESAFE_API_KEY)},
                {"name": "NAVER API HUB", "model": "뉴스 검색", "configured": bool(NAVER_CLIENT_ID and NAVER_CLIENT_SECRET)}],
            "note": "설정됨은 키를 읽었다는 뜻이며 인증·잔액 확인 결과가 아닙니다."}


@app.get("/chats")
def chats():
    return {"chats": list_chats()}


@app.post("/chats")
def create_chat():
    global active_chat_id
    with locked():
        state = new_chat(create_messages())
        save_chat(state)
        active_chat_id = state["chat_id"]
        return snapshot(state)


@app.get("/chats/current")
def current_chat():
    with locked():
        return snapshot(get_chat())


@app.get("/chats/{chat_id}")
def read_chat(chat_id: str):
    return snapshot(get_chat(chat_id))


@app.get("/usage")
def usage(chat_id: str | None = None):
    states = [get_chat(chat_id)] if chat_id else [load_chat(row["id"]) for row in list_chats()]
    records = [u for s in states for t in s["turns"] for u in (t.get("usage") or [])]
    return {"summary": summarize_usage(records), "records": records,
            "scope": "현재 대화" if chat_id else "저장된 전체 대화",
            "note": "이 앱에서 수집한 사용량입니다. 계정 전체 잔액·청구액이 아니며 재시도 등 미수신 사용량은 제외됩니다."}


@app.post("/chats/{chat_id}/files")
def upload(chat_id: str, file: UploadFile = File(...)):
    with locked():
        state = get_chat(chat_id)
        name = (file.filename or "file").replace('\\', '/').rsplit('/', 1)[-1]
        suffix = Path(name).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
            raise HTTPException(400, "지원하지 않는 파일 형식입니다.")
        safe_name = re.sub(r'[^\w.\- ]', '_', name)[:120]
        path = Path(UPLOAD_DIR) / f"{uuid4().hex}_{safe_name}"
        count = 0
        digest = hashlib.sha256()
        try:
            with path.open('wb') as target:
                while chunk := file.file.read(1024 * 1024):
                    count += len(chunk)
                    if count > MAX_UPLOAD_MB * 1024 * 1024:
                        raise HTTPException(413, f"파일당 {MAX_UPLOAD_MB}MB까지 등록할 수 있습니다.")
                    digest.update(chunk)
                    target.write(chunk)
            if count == 0:
                raise HTTPException(400, "빈 파일입니다.")
            identity = (name, digest.hexdigest())
            if identity in state["upload_keys"]:
                path.unlink(missing_ok=True)
                return {"files": public_files(state), "message": "이미 등록한 파일입니다."}
            state["files"].append({"name": name, "path": str(path.resolve())})
            state["upload_keys"].add(identity)
            save_chat(state)
            return {"files": public_files(state), "message": "파일 등록 완료"}
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()


@app.get("/chats/{chat_id}/files/{index}")
def download(chat_id: str, index: int):
    state = get_chat(chat_id)
    try:
        if index < 0:
            raise IndexError
        item = state["files"][index]
        path = allowed_path(item["path"])
    except (IndexError, ValueError, OSError) as error:
        raise HTTPException(404, "파일을 찾을 수 없습니다.") from error
    return FileResponse(path, filename=item["name"])


def run_agent(req, state, emit):
    """호출자는 lock을 소유한다. 스트림 연결이 끊겨도 worker는 결과를 저장한다."""
    started = perf_counter()
    records, results = [], []
    turn = {"question": req.message.strip(), "answer": "", "results": results,
            "files": [], "error": None, "usage": records, "elapsed": 0}

    def usage_sink(event):
        if event.get("type") == "usage":
            records.append(event["data"])
            emit(event)

    token = USAGE_SINK.set(usage_sink)
    done = None
    try:
        try:
            for event in stream_agent(req.message.strip(), history=state["messages"],
                                      files=state["files"], force_judgment=req.force_judgment,
                                      continue_case=req.continue_case):
                kind = event.get("type")
                if kind == "done":
                    done = event
                elif kind == "tool_result":
                    results.append({"name": event["name"], "label": event.get("label", event["name"]),
                                    "data": event["data"]})
                    emit(event)
                else:
                    emit(event)
            if done is None:
                raise RuntimeError("최종 답변을 받지 못했습니다.")
            turn["answer"] = done["answer"]
            state["messages"] = done["messages"]
        except Exception:
            logger.exception("에이전트 실행 실패")
            turn["error"] = "처리에 실패했습니다. 서버 터미널을 확인해주세요. 수신한 사용량과 도구 결과는 보존합니다."
        turn["files"] = generated_files(state, results)
        turn["elapsed"] = perf_counter() - started
        state["turns"].append(turn)
        try:
            save_chat(state)
        except Exception:
            logger.exception("대화 저장 실패")
            turn["error"] = "대화 저장에 실패했습니다. 화면의 답변을 복사하고 서버 로그를 확인해주세요."
            emit({"type": "error", "message": "대화 저장에 실패했습니다. 화면의 답변을 복사하고 서버 로그를 확인해주세요.",
                  "turn": public_turn(state, turn)})
            return turn
        emit({"type": "done", "chat_id": state["chat_id"], "turn": public_turn(state, turn),
              "files": public_files(state)})
        return turn
    finally:
        USAGE_SINK.reset(token)


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "질문을 입력해주세요.")
    with locked():
        state = get_chat(req.chat_id)
        turn = run_agent(req, state, lambda event: None)
        if turn["error"]:
            raise HTTPException(500, turn["error"])
        return {"answer": turn["answer"], "chat_id": state["chat_id"],
                "turn": public_turn(state, turn), "files": public_files(state)}


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "질문을 입력해주세요.")
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(409, "처리 중인 요청이 있습니다. 완료 후 대화를 다시 열어주세요.")
    try:
        state = get_chat(req.chat_id)
    except Exception:
        chat_lock.release()
        raise
    queue = Queue()

    def worker():
        try:
            run_agent(req, state, queue.put)
        except Exception:
            logger.exception("요청 처리 실패")
            queue.put({"type": "error", "message": "서버 처리에 실패했습니다. 서버 로그를 확인해주세요."})
        finally:
            chat_lock.release()
            queue.put(None)

    def events():
        while True:
            try:
                event = queue.get(timeout=10)
            except Empty:
                yield '{"type":"heartbeat"}\n'
                continue
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False, default=str) + '\n'

    Thread(target=worker, daemon=True).start()
    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
