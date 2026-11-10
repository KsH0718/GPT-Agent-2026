import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일 로드
load_dotenv()

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return OpenAI(api_key=api_key)

def ask_question(client, question, model="gpt-4o", temperature=0.1):
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question},
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"오류가 발생했습니다: {e}"

def run_predefined_questions(client):
    questions = [
        "대한민국 노원 월계동에 있는 인덕대학교의 설립 날짜를 알려줘",
        "인덕대학교의 위치는 어디야?",
        "인덕대학교는 어떤 학교야?",
        "인덕대학교의 전공 분야를 간단히 설명해줘"
    ]

    for i, question in enumerate(questions, start=1):
        print(f"\n질문 {i}: {question}")
        print("답변:")
        answer = ask_question(client, question)
        print(answer)
        print("-" * 60)

def run_chat_loop(client):
    print("\n질문을 입력하세요. 종료하려면 'q' 또는 'quit'를 입력하세요.")
    
    while True:
        question = input("\n질문: ").strip()
        
        if question.lower() in ("q", "quit", "exit"):
            print("프로그램을 종료합니다.")
            break
        
        answer = ask_question(client, question)
        print("\n답변:")
        print(answer)
        print("-" * 60)

if __name__ == "__main__":
    try:
        client = get_client()

        mode = input("모드를 선택하세요.\n1: 미리 정의된 질문\n2: 대화형 질문\n선택: ").strip()

        if mode == "1":
            run_predefined_questions(client)
        elif mode == "2":
            run_chat_loop(client)
        else:
            print("잘못된 선택입니다. 기본값으로 대화형 질문 모드를 실행합니다.")
            run_chat_loop(client)

    except Exception as e:
        print(f"\n프로그램 실행 중 오류가 발생했습니다: {e}")