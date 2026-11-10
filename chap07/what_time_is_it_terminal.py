from gpt_functions import get_current_time, tools
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
import streamlit as st


# 페이지 설정
st.set_page_config(
    page_title="시간 안내 챗봇",
    page_icon="🕒",
)

st.title("🕒 Chat Bot")
st.caption("궁금한 지역의 현재 시간을 물어보세요.")


# .env 파일에서 API 키 불러오기
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    st.error("OPENAI_API_KEY가 없습니다. .env 파일을 확인해 주세요.")
    st.stop()

client = OpenAI(api_key=api_key)


def get_ai_response(messages, tools=None):
    """대화 기록과 도구 목록을 전달하여 AI 응답을 받는다."""
    return client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=tools,
    )


def create_initial_messages():
    """새 대화의 시스템 지침과 시작 인사말을 만든다."""
    return [
        {
            "role": "system",
            "content": (
                "너는 사용자를 도와주는 친절한 상담사야. "
                "사용자가 시간을 물어보면 대화 맥락에서 "
                "지역이나 타임존이 명확한지 먼저 판단해. "
                "지역이나 타임존을 알 수 없으면 "
                "'어느 지역의 시간을 알고 싶으신가요? "
                "특정 타임존이 있으면 말씀해 주세요.'라고 먼저 물어봐. "
                "지역이나 타임존이 있으면 get_current_time 도구를 사용해. "
                "여러 시간대가 있는 나라라면 기준 도시를 답변에 명시해. "
                "도구 실행 결과를 받으면 자연스럽고 짧게 답변해. "
                "도구가 오류를 반환하면 시간을 추측하지 말고 알려줘."
            ),
        },
        {
            "role": "assistant",
            "content": "안녕하세요. 무엇을 도와드릴까요?",
        },
    ]


def generate_answer(messages):
    """함수 호출을 처리하고 최종 답변을 반환한다."""
    # 도구 호출이 반복되는 경우를 고려하되 최대 요청 횟수를 제한한다.
    for _ in range(5):
        response = get_ai_response(messages, tools=tools)
        ai_message = response.choices[0].message

        # 도구 호출 요청을 포함한 AI 메시지를 먼저 저장한다.
        messages.append(ai_message.model_dump(exclude_none=True))

        # 도구 호출이 없으면 최종 답변을 반환한다.
        if not ai_message.tool_calls:
            return ai_message.content or "답변을 생성하지 못했습니다."

        # 요청된 모든 도구 호출을 처리한다.
        for tool_call in ai_message.tool_calls:
            tool_name = tool_call.function.name

            try:
                arguments = json.loads(
                    tool_call.function.arguments or "{}"
                )

                if not isinstance(arguments, dict):
                    raise ValueError("함수 인자는 JSON 객체여야 합니다.")

                if tool_name == "get_current_time":
                    timezone = arguments.get("timezone", "Asia/Seoul")

                    if not isinstance(timezone, str):
                        raise ValueError("timezone은 문자열이어야 합니다.")

                    tool_result = get_current_time(timezone=timezone)
                else:
                    tool_result = f"오류: 지원하지 않는 함수: {tool_name}"

            except (ValueError, TypeError) as e:
                tool_result = f"함수 인자 오류: {e}"
            except Exception as e:
                tool_result = f"시간 조회 중 오류가 발생했습니다: {e}"

            # 각 도구 요청에 대응하는 결과를 기록한다.
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(tool_result),
            })

    raise RuntimeError("도구 호출이 반복되고 있습니다. 다시 질문해 주세요.")


# Streamlit이 다시 실행되어도 대화 기록을 유지한다.
if "messages" not in st.session_state:
    st.session_state.messages = create_initial_messages()


# 사이드바의 새 대화 버튼
with st.sidebar:
    st.header("대화 설정")

    if st.button("새 대화 시작"):
        st.session_state.messages = create_initial_messages()
        st.rerun()

    st.caption("예: 지금 몇 시야? / 서울 시간 알려줘 / 뉴욕은?")


# 기존 대화 표시
# 시스템 지침과 도구 실행 기록은 화면에 표시하지 않는다.
for message in st.session_state.messages:
    if (
        message["role"] in ("user", "assistant")
        and message.get("content")
        and not message.get("tool_calls")
    ):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


# 웹 채팅 입력창
user_input = st.chat_input("메시지를 입력하세요.")

if user_input and user_input.strip():
    user_input = user_input.strip()

    # 사용자 메시지 표시
    with st.chat_message("user"):
        st.markdown(user_input)

    # 처리 중 오류가 나도 기존 대화 기록이 손상되지 않도록
    # 임시 목록에서 작업한 후 성공했을 때 저장한다.
    working_messages = [
        *st.session_state.messages,
        {"role": "user", "content": user_input},
    ]

    with st.chat_message("assistant"):
        try:
            with st.spinner("답변을 준비하고 있어요..."):
                answer = generate_answer(working_messages)

            st.markdown(answer)

            # 최종 답변까지 정상 처리되면 대화 기록을 저장한다.
            st.session_state.messages = working_messages

        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
            st.info("질문을 다시 입력해 주세요.")