# integrated_agent/app.py
"""통합 AI 에이전트의 Streamlit 화면."""

from usage_tracking import USAGE_SINK, summarize_usage

import hashlib
import time
from queue import Queue, Empty
from threading import Thread
from copy import deepcopy
from pathlib import Path

from chat_store import new_chat, save_chat, load_chat, list_chats

import pandas as pd
import streamlit as st

from config import OPENAI_API_KEY, MAX_UPLOAD_MB, OUTPUT_DIR, TYPESAFE_API_KEY, JEV_MODEL
from file_utils import (
    ALLOWED_UPLOAD_EXTENSIONS,
    save_uploaded_file,
    resolve_input_file,
)
from agent import (
    ALL_TOOLS,
    create_messages,
    stream_agent,
)


st.set_page_config(
    page_title="통합 AI 에이전트",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 통합 AI 에이전트")
st.caption(
    "문서 요약·보고서 생성 · 음성 인식 · 이미지 분석·퀴즈 · 주가·뉴스·시간"
)


# ---------------------------------------------------------
# 1. 세션 상태
# ---------------------------------------------------------

STATE_KEY = "integrated_agent_v1"

try:
    if STATE_KEY not in st.session_state:
        saved_chats = list_chats()
        state = (load_chat(saved_chats[0]["id"]) if saved_chats
                 else new_chat(create_messages()))
        st.session_state[STATE_KEY] = state
    state = st.session_state[STATE_KEY]
    # 업데이트 전부터 열려 있던 세션은 표시 중인 내용을 보존한다.
    if "chat_id" not in state:
        state.update({k: v for k, v in new_chat([]).items() if k not in state})
    if state["revision"] == 0:
        save_chat(state)
except Exception as error:
    st.error(f"대화 저장소를 열지 못했습니다: {error}")
    st.stop()

state.setdefault("job", None)
busy = state["job"] is not None
if st.session_state.pop("reset_case", False):
    st.session_state["continue_case"] = False


def persist_chat():
    try:
        save_chat(state)
        st.session_state.pop("chat_save_error", None)
        return True
    except Exception as error:
        st.session_state["chat_save_error"] = str(error)
        return False



def agent_worker(events, question, history, files, force_judgment=False, continue_case=False):
    """작업 스레드는 Streamlit과 세션 상태에 접근하지 않는다."""
    usage_token = USAGE_SINK.set(events.put)
    try:
        for event in stream_agent(question=question, history=history, files=files, force_judgment=force_judgment, continue_case=continue_case):
            events.put(event)
    except Exception as error:
        events.put({"type": "worker_error", "text":
                    f"{type(error).__name__}: {error}"})
    finally:
        USAGE_SINK.reset(usage_token)
        events.put({"type": "worker_finished"})


def elapsed_label(seconds):
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes}분 {seconds:02d}초" if minutes else f"{seconds}초"



def register_file(name: str, path: str):
    """현재 세션의 파일 목록에 등록한다."""
    resolved = str(resolve_input_file(path))

    if not any(item["path"] == resolved for item in state["files"]):
        state["files"].append({
            "name": name,
            "path": resolved,
        })


def collect_generated_files(record: dict) -> list[dict]:
    """파일 생성 도구가 반환한 결과만 다운로드 대상으로 등록한다."""
    if record["name"] not in {"create_report", "transcribe_audio"}:
        return []

    data = record["data"]

    if not isinstance(data, dict) or not data.get("성공"):
        return []

    candidates = (
        data.get("생성 파일", [])
        if record["name"] == "transcribe_audio"
        else [data]
    )

    files = []

    for item in candidates:
        try:
            path = resolve_input_file(item["파일 경로"])

            if not path.is_relative_to(OUTPUT_DIR.resolve()):
                continue

            register_file(path.name, str(path))

            files.append({
                "name": path.name,
                "path": str(path),
            })

        except (KeyError, TypeError, ValueError, OSError):
            continue

    return files


def show_downloads(files: list[dict], prefix: str):
    """존재하는 결과 파일의 다운로드 버튼을 표시한다."""
    seen = set()

    for index, item in enumerate(files):
        if item["path"] in seen:
            continue

        seen.add(item["path"])

        try:
            path = resolve_input_file(item["path"])

            if not path.is_relative_to(OUTPUT_DIR.resolve()):
                continue

            st.download_button(
                label=f"📥 {item['name']}",
                data=path.read_bytes(),
                file_name=item["name"],
                key=f"{prefix}_download_{index}",
                disabled=busy,
            )

        except (ValueError, OSError):
            st.caption(f"파일을 찾을 수 없습니다: {item['name']}")


def show_usage(turns, detailed=False):
    records = [item for turn in turns for item in turn.get("usage", [])]
    token_records = [item for item in records if item.get("model") != "Whisper"]
    if token_records:
        st.dataframe(summarize_usage(token_records), hide_index=True, use_container_width=True)
    else:
        st.caption("아직 수집된 토큰 기록이 없습니다.")
    old_count = sum("usage" not in turn for turn in turns)
    if old_count:
        st.caption(f"업데이트 전 대화 {old_count}건은 사용량 기록이 없어 합산에서 제외됩니다.")
    for item in records:
        if item.get("model") == "Whisper":
            st.caption(item["note"])
    if detailed and records:
        with st.expander("호출별 사용량 상세"):
            st.dataframe([{
                "서비스": r["provider"], "모델": r["model"], "단계": r["stage"],
                "입력": str(r["input_tokens"]) if r["input_tokens"] is not None else "확인 불가",
                "출력": str(r["output_tokens"]) if r["output_tokens"] is not None else "확인 불가",
                "합계": str(r["total_tokens"]) if r["total_tokens"] is not None else "확인 불가",
                "안내": r["note"],
            } for r in records], hide_index=True, use_container_width=True)


def show_judgments(records):
    """관찰 사실과 가설을 구분하고, 보류된 값에는 막대를 그리지 않는다."""
    for record in records:
        if record.get("name") != "evaluate_judgment":
            continue
        data = record.get("data")
        st.markdown("#### 🧭 Jev 판단 분석")
        if not isinstance(data, dict) or not data.get("성공"):
            st.info("평가 안 됨")
            if isinstance(data, dict):
                st.caption(data.get("오류", "유효한 결과가 없습니다."))
            continue
        st.caption("근거 범위: " + data.get("근거 범위", "이전 버전 결과 · 새로 평가해주세요"))
        rows = data.get("가설별 확률", [])
        if not rows:
            st.write("**평가한 주장:**", data["평가한 주장"])
            st.write("**판정:**", data["판정"])
            confidence = data.get("판단 확신도")
            if data.get("판정 코드") == "insufficient":
                st.warning("판단 보류 · 근거 부족. 확신도 막대를 표시하지 않습니다.")
            elif confidence is not None:
                st.progress(float(confidence), text=f"이 주장에 대한 판정 확신도 · {confidence * 100:.1f}%")
            with st.expander("판정별 모델 확률"):
                probs = data.get("판정별 확률", {})
                if not probs:
                    st.caption("근거 부족으로 수치를 표시하지 않습니다.")
                for label, value in probs.items():
                    st.progress(float(value), text=f"{label} · {value * 100:.1f}%")
        else:
            st.caption("가설마다 따로 평가합니다. 전체 분석을 대표하는 확신도는 만들지 않습니다.")
            for row in rows:
                st.write("**가설:**", row["가설"])
                st.write("**근거 판정:**", row.get("판정", "이전 버전 결과"))
                value = row.get("확률")
                if value is None:
                    st.info(row.get("확률 상태", "확률 산출 보류"))
                else:
                    st.progress(float(value), text=f"가설의 모델 추정 확률 · {value * 100:.1f}%")
                    st.caption("수학적으로 계산한 값과 다를 수 있습니다. 실제 정답률이 아닙니다.")
                # 높은 확신도는 그 판정에만 해당하며 사건 자체의 발생 확률이 아니다.
                conf = row.get("판단 확신도")
                if conf is not None and row.get("판정 코드") != "insufficient":
                    with st.expander("이 가설의 근거 판정 확신도"):
                        st.progress(float(conf), text=f"판정 분포 집중도 · {conf * 100:.1f}%")
                st.divider()
            st.caption("가설은 동시에 성립할 수 있습니다. 표시된 확률을 더해 100%로 맞추지 않습니다.")
        st.caption("근거 충분성 검사도 모델의 판단입니다. 높은 확신도가 사실의 진위나 사람의 속마음을 보증하지 않습니다.")
        with st.expander("평가에 사용한 근거 자료 보기"):
            st.text(data.get("평가에 사용한 자료", ""))
        st.caption(f"평가 모델: {data.get('모델', JEV_MODEL)}")


def show_tool_result(record: dict):
    """도구 실행 결과를 접을 수 있는 영역으로 표시한다."""
    if record.get("name") == "evaluate_judgment":
        return  # 답변 아래의 별도 UI에서 표시
    data = record["data"]

    with st.expander(record["label"], expanded=False):
        if not isinstance(data, dict):
            st.write(data)
            return

        if data.get("오류"):
            st.warning(str(data["오류"]))
            return

        if "뉴스" in data:
            for article in data["뉴스"]:
                st.write(f"**{article.get('제목', '')}**")
                st.caption(article.get("제공 시각", ""))
                st.write(article.get("요약문", ""))

                link = article.get("네이버 뉴스 링크")

                if link:
                    st.link_button("기사 읽기", link)

                st.divider()

        elif "주가" in data:
            frame = pd.DataFrame(data["주가"])

            if not frame.empty:
                st.dataframe(frame, use_container_width=True)

                if {"날짜", "종가"}.issubset(frame.columns):
                    st.line_chart(
                        frame.set_index("날짜")[["종가"]]
                    )

        elif "비교표" in data:
            st.dataframe(
                pd.DataFrame(data["비교표"]),
                use_container_width=True,
            )
            st.write(
                f"종가 변동률: {data.get('종가 변동률(%)', '정보 없음')}%"
            )

        elif "투자의견" in data:
            st.dataframe(
                pd.DataFrame(data["투자의견"]),
                use_container_width=True,
            )

        elif "종목 후보" in data:
            st.dataframe(
                pd.DataFrame(data["종목 후보"]),
                use_container_width=True,
            )

        elif "결과" in data:
            # 이미지 퀴즈 원본도 이곳에서 확인할 수 있다.
            st.markdown(data["결과"])

        elif "텍스트" in data:
            st.markdown(str(data["텍스트"]).replace("\n", "  \n"))

        elif "내용" in data:
            st.markdown(str(data["내용"]).replace("\n", "  \n"))

            if data.get("남은 내용 있음"):
                st.caption("문서의 일부 구간입니다.")

        elif data.get("성공"):
            st.success("파일 생성 완료")

        else:
            st.json(data)

        for key in ("안내", "참고", "CSV 안내"):
            if data.get(key):
                st.caption(str(data[key]))


# ---------------------------------------------------------
# 2. 사이드바: 대화 초기화와 파일 업로드
# ---------------------------------------------------------

with st.sidebar:
    with st.popover("⚙️ 사용량 설정", use_container_width=True):
        st.subheader("현재 대화 토큰 사용량")
        usage_sidebar = st.empty()
        with usage_sidebar.container():
            show_usage(state["turns"], detailed=True)
        st.caption("입력에는 대화 기록·도구 정의 등이 포함됩니다. 이 앱에서 수집한 값이며 계정 전체 사용량·잔액은 아닙니다. 재시도·중단 시 미수신 사용량은 빠질 수 있습니다.")
    st.divider()
    st.header("대화 설정")
    force_judgment = st.checkbox(
        "이번 답변의 근거·확신도 평가", value=False, disabled=busy,
        help="선택하면 최종 답변 전 Jev 평가를 요청합니다. 해제해도 확률·근거 분석을 직접 요청하면 도구를 사용할 수 있습니다.",
    )
    continue_case = st.checkbox("같은 사건 이어서 분석", value=False, disabled=busy, key="continue_case",
        help="새 문제는 해제하세요. 체크하면 마지막으로 시작한 판단 사건의 최근 기록을 함께 사용합니다.")
    st.caption("새 판단 문제는 이전 대화와 분리합니다. 같은 사건의 추가 증거를 줄 때만 이어서 분석을 체크하세요.")
    st.caption("Jev 판단 분석은 TypeSafe API를 사용하며 평가 자료가 전송됩니다.")
    st.caption("Jev 키: " + ("불러옴 · 요청 시 자동 인증" if TYPESAFE_API_KEY else "없음 · 평가 안 됨"))
    st.caption("별도 인증 버튼은 없습니다. 키의 유효성은 실제 평가 요청 때 확인합니다.")
    last_judgment = next((record.get("data")
        for turn in reversed(state["turns"])
        for record in reversed(turn.get("results", []))
        if record.get("name") == "evaluate_judgment"), None)
    if isinstance(last_judgment, dict):
        st.caption("이 대화의 최근 Jev 평가: " +
                   ("성공" if last_judgment.get("성공") else "실패 · 결과의 오류 안내 확인"))
    typing_delay = st.slider(
        "답변 출력 지연 (초/조각)",
        min_value=0.0,
        max_value=0.20,
        value=0.04,
        step=0.01,
        key="typing_delay",
        disabled=busy,
    )

    st.caption("0이면 즉시 표시하고, 값이 클수록 천천히 표시합니다.")
    st.caption(f"연결된 도구: {len(ALL_TOOLS)}개")

    st.subheader("대화 보관함")
    if st.session_state.get("chat_save_error"):
        st.error("대화를 저장하지 못했습니다: " + st.session_state["chat_save_error"])
        if st.button("대화 저장 다시 시도", disabled=busy):
            persist_chat()
            st.rerun()

    if st.button("새 대화 시작", use_container_width=True, disabled=busy):
        if persist_chat():
            candidate = new_chat(create_messages())
            try:
                save_chat(candidate)
            except Exception as error:
                st.error(f"새 대화를 저장하지 못했습니다: {error}")
            else:
                st.session_state[STATE_KEY] = candidate
                st.session_state["reset_case"] = True
                st.rerun()
        else:
            st.rerun()

    try:
        conversations = list_chats()
        labels = {item["id"]: f"{item['title']} · {item['updated_at'][:16].replace('T', ' ')}"
                  for item in conversations}
        ids = list(labels)
        selected_chat = st.selectbox(
            "저장된 대화", options=ids,
            index=ids.index(state["chat_id"]),
            format_func=lambda chat_id: labels[chat_id],
            key=f"chat_picker_{state['chat_id']}", disabled=busy)
        if st.button("선택한 대화 열기", use_container_width=True,
                     disabled=busy or selected_chat == state["chat_id"]):
            if persist_chat():
                st.session_state[STATE_KEY] = load_chat(selected_chat)
                st.session_state["reset_case"] = True
                st.rerun()
            else:
                st.rerun()
    except Exception as error:
        st.error(f"대화 목록을 읽지 못했습니다: {error}")
    st.caption("새 대화를 시작해도 이전 대화와 파일 목록은 보관됩니다. 앱을 다시 켜도 열 수 있습니다.")

    st.divider()
    st.subheader("파일 업로드")
    st.caption(f"파일당 최대 {MAX_UPLOAD_MB}MB")

    uploaded_files = st.file_uploader(
        "문서·이미지·음성을 선택하세요.",
        type=sorted(
            extension.lstrip(".")
            for extension in ALLOWED_UPLOAD_EXTENSIONS
        ),
        accept_multiple_files=True,
        key=f"uploads_{state['chat_id']}_{state['uploader_version']}",
        disabled=busy,
    )

    if st.button("선택한 파일 등록", use_container_width=True, disabled=busy):
        if not uploaded_files:
            st.info("먼저 파일을 선택해주세요.")

        for uploaded in uploaded_files or []:
            try:
                if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise ValueError(
                        f"파일당 {MAX_UPLOAD_MB}MB 제한을 초과했습니다."
                    )

                digest = hashlib.sha256(
                    uploaded.getbuffer()
                ).hexdigest()

                identity = (uploaded.name, digest)

                if identity in state["upload_keys"]:
                    st.caption(f"이미 등록됨: {uploaded.name}")
                    continue

                saved_path = save_uploaded_file(uploaded)
                register_file(uploaded.name, str(saved_path))
                state["upload_keys"].add(identity)

                st.success(f"등록 완료: {uploaded.name}")

            except Exception as error:
                st.error(f"{uploaded.name}: {error}")

        if uploaded_files and not persist_chat():
            st.error("파일 목록 저장 실패: " + st.session_state["chat_save_error"])

    st.divider()
    st.subheader("현재 파일")

    if not state["files"]:
        st.caption("등록된 파일이 없습니다.")

    for index, item in enumerate(state["files"], start=1):
        st.caption(f"{index}. {item['name']}")

    st.divider()
    st.caption(
        "음성은 기본적으로 로컬 Whisper로 처리합니다. "
        "이미지 분석·대화·요약에는 OpenAI API를 사용합니다."
    )
    st.caption(
        "대화 기록은 이 PC에 저장되며, "
        "모델에는 최근 기록 일부가 전달됩니다."
    )


# ---------------------------------------------------------
# 3. 등록한 이미지 미리보기
# ---------------------------------------------------------

image_files = [
    item
    for item in state["files"]
    if Path(item["path"]).suffix.lower()
    in {".jpg", ".jpeg", ".png", ".webp"}
]

if image_files:
    with st.expander("등록한 이미지 보기", expanded=False):
        for item in image_files:
            try:
                st.image(
                    item["path"],
                    caption=item["name"],
                    width=320,
                )
            except Exception:
                st.warning(f"미리보기 실패: {item['name']}")


# ---------------------------------------------------------
# 4. 기존 대화 표시
# ---------------------------------------------------------

if not state["turns"]:
    st.info(
        "파일을 등록하고 원하는 작업을 입력하세요. "
        "예: 이 PDF를 요약해서 Word로 저장해줘."
    )

for turn_index, turn in enumerate(state["turns"]):
    if busy and turn_index == state["job"]["turn_index"]:
        continue
    with st.chat_message("user"):
        st.markdown(turn["question"])

    with st.chat_message("assistant"):
        for record in turn["results"]:
            show_tool_result(record)

        if turn["answer"]:
            st.markdown(turn["answer"])

        show_judgments(turn["results"])
        with st.expander("이 답변의 토큰 사용량"):
            show_usage([turn], detailed=True)

        if "elapsed" in turn:
            label = "처리 실패" if turn.get("error") else "처리 완료"
            st.caption(f"{label} · 총 {elapsed_label(turn['elapsed'])}")

        if turn.get("error"):
            st.error(turn["error"])

        show_downloads(
            turn["files"],
            prefix=f"history_{turn_index}",
        )


# ---------------------------------------------------------
# 5. 사용자 입력과 에이전트 실행
# ---------------------------------------------------------

if not OPENAI_API_KEY:
    st.error("OPENAI_API_KEY를 찾지 못했습니다. config.py 설정을 확인해주세요.")
    st.stop()

question = st.chat_input(
    "예: 이 음성을 회의록으로 정리해서 Word로 저장해줘.",
    disabled=busy,
)

if question and question.strip() and not busy:
    question = question.strip()
    turn = {
        "question": question, "answer": "", "results": [],
        "files": [], "error": None, "partial": "", "usage": [],
    }
    events = Queue()
    # 작업에 전달할 데이터를 복사하여 화면 상태와 분리한다.
    worker = Thread(
        target=agent_worker,
        args=(events, question, deepcopy(state["messages"]),
              deepcopy(state["files"]), force_judgment, continue_case),
        daemon=True,
    )
    state["turns"].append(turn)
    state["job"] = {
        "events": events, "worker": worker,
        "turn_index": len(state["turns"]) - 1,
        "started": time.monotonic(), "status": "요청을 분석하고 있어요…",
        "done": None,
    }
    worker.start()
    # 입력 위젯들을 잠그고, 실행 중인 작업을 이어서 표시한다.
    st.rerun()

if state["job"] is not None:
    job = state["job"]
    turn = state["turns"][job["turn_index"]]
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        status_box = st.empty()
        st.caption("경과 시간은 요청부터 화면 출력까지의 시간입니다. 완료 예상 시간은 아닙니다.")
        answer_box = st.empty()
        result_box = st.container()
        judgment_box = st.empty()
        if turn["partial"]:
            answer_box.markdown(turn["partial"])
        with result_box:
            for record in turn["results"]:
                show_tool_result(record)

        with judgment_box.container():
            show_judgments(turn["results"])

        finished = False
        last_refresh = 0.0
        with st.spinner("작업 중입니다. 음성 인식은 시간이 걸릴 수 있어요."):
            while not finished:
                now = time.monotonic()
                if now - last_refresh >= 0.2:
                    status_box.info(
                        f"⏳ {job['status']}  ·  "
                        f"{elapsed_label(now - job['started'])} 경과"
                    )
                    last_refresh = now
                try:
                    event = job["events"].get(timeout=0.1)
                except Empty:
                    if not job["worker"].is_alive():
                        # 정상 종료 시에는 큐에 종료 이벤트가 먼저 들어간다.
                        if job["events"].empty():
                            turn["error"] = "작업이 완료 응답 없이 종료되었습니다."
                            finished = True
                    continue

                kind = event["type"]
                if kind == "status":
                    job["status"] = event["text"]
                    last_refresh = 0.0
                elif kind == "reset":
                    turn["partial"] = ""
                    answer_box.empty()
                elif kind == "token":
                    job["status"] = "답변을 작성하고 있어요…"
                    turn["partial"] += event["text"]
                    answer_box.markdown(turn["partial"])
                    if typing_delay > 0:
                        time.sleep(typing_delay)
                elif kind == "tool_result":
                    record = {key: event[key] for key in ("name", "label", "data")}
                    turn["results"].append(record)
                    turn["files"].extend(collect_generated_files(record))
                    job["status"] = "도구 결과를 정리하고 있어요…"
                    with result_box:
                        show_tool_result(record)
                    if record["name"] == "evaluate_judgment":
                        with judgment_box.container():
                            show_judgments(turn["results"])
                elif kind == "usage":
                    turn.setdefault("usage", []).append(event["data"])
                    with usage_sidebar.container():
                        show_usage(state["turns"], detailed=True)
                elif kind == "done":
                    # 실제 작업 종료를 확인한 후에만 대화 기록을 확정한다.
                    job["done"] = event
                elif kind == "worker_error":
                    turn["error"] = f"처리 중 오류가 발생했습니다: {event['text']}"
                elif kind == "worker_finished":
                    finished = True

        if not turn["error"] and job["done"] is not None:
            turn["answer"] = job["done"]["answer"]
            state["messages"] = job["done"]["messages"]
        else:
            turn["error"] = turn["error"] or "완료 응답을 받지 못했습니다. 다시 질문해주세요."
            turn["error"] += (
                " 이번 질문은 모델의 대화 기록에 반영되지 않았습니다. "
                "이미 생성된 파일은 아래에서 다운로드할 수 있습니다."
            )
        turn["elapsed"] = time.monotonic() - job["started"]
        turn.pop("partial", None)
        state["job"] = None
        persist_chat()
        st.rerun()


st.caption(
    "뉴스는 검색 제목·요약문 기반이며, "
    "음성 인식 결과에는 화자 구분이 포함되지 않습니다."
)

# ===============================================
# python -m streamlit run app.py 실행하면 됨.
# ===============================================