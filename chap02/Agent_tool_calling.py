import os 
import json
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd  # pip install pandas openpyxl
from docx import Document # pip install python-docx
import fitz # pip install pymupdf
from reportlab.lib.pagesizes import A4 # pip install reportlab
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from xml.sax.saxutils import escape

load_dotenv()

MAX_DOCUMENT_CHARS = 40000


def _tool_schema(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
            },
        },
    }


FILE_PROPERTY = {
    "file_name": {"type": "string", "description": "파일 경로"},
}
REPORT_PROPERTIES = {
    "file_name": {"type": "string", "description": "저장할 파일 경로"},
    "title": {"type": "string", "description": "보고서 제목"},
    "content": {"type": "string", "description": "보고서 본문 내용 및 요약"},
}

def get_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    return OpenAI(api_key=api_key)


# Agent가 사용할 실제 도구
def create_excel_report(file_name: str, title: str, content: str) -> str:
    """요약된 텍스트 내용으로 엑셀 파일(.xlsx)을 생성합니다."""
    try:
        df = pd.DataFrame([{"제목": title, "내용": content}])
        df.to_excel(file_name, index=False)
        return f"성공적으로 {file_name} 파일이 생성되었습니다."
    except Exception as error:
        return f"엑셀 생성 실패: {error}"


def create_word_report(file_name: str, title: str, content: str) -> str:
    """요약된 텍스트 내용으로 Word 파일(.docx)을 생성합니다."""
    try:
        document = Document()
        document.add_heading(title, level=1)
        document.add_paragraph(content)
        document.save(file_name)
        return f"성공적으로 {file_name} 파일이 생성되었습니다."
    except Exception as error:
        return f"Word 생성 실패: {error}"


def create_pdf_report(file_name: str, title: str, content: str) -> str:
    """요약된 텍스트 내용으로 PDF 파일(.pdf)을 생성합니다."""
    try:
        font_name = "Helvetica"
        korean_font_path = "C:/Windows/Fonts/malgun.ttf"
        if os.path.exists(korean_font_path):
            pdfmetrics.registerFont(TTFont("MalgunGothic", korean_font_path))
            font_name = "MalgunGothic"

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName=font_name,
            alignment=TA_CENTER,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontName=font_name,
            leading=18,
        )

        document = SimpleDocTemplate(file_name, pagesize=A4)
        story = [
            Paragraph(escape(title), title_style),
            Spacer(1, 20),
            Paragraph(escape(content).replace("\n", "<br/>") , body_style),
        ]
        document.build(story)
        return f"성공적으로 {file_name} 파일이 생성되었습니다."
    except Exception as error:
        return f"PDF 생성 실패: {error}"


def read_excel_file(file_name: str) -> str:
    """Excel 파일의 내용을 텍스트로 읽습니다."""
    try:
        sheets = pd.read_excel(file_name, sheet_name=None)
        sections = []
        for sheet_name, data_frame in sheets.items():
            sections.append(f"[시트: {sheet_name}]\n{data_frame.to_string(index=False)}")
        return "\n\n".join(sections)[:MAX_DOCUMENT_CHARS]
    except Exception as error:
        return f"Excel 읽기 실패: {error}"


def read_word_file(file_name: str) -> str:
    """Word 파일의 문단 텍스트를 읽습니다."""
    try:
        document = Document(file_name)
        text = "\n".join(
            paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()
        )
        return text[:MAX_DOCUMENT_CHARS]
    except Exception as error:
        return f"Word 읽기 실패: {error}"


def read_pdf_file(file_name: str) -> str:
    """PDF 파일의 페이지 텍스트를 PyMuPDF로 추출합니다."""
    try:
        document = fitz.open(file_name)
        pages = []
        current_length = 0

        for page_number, page in enumerate(document, start=1):
            page_text = page.get_text().strip()
            if not page_text:
                continue

            section = f"[페이지 {page_number}]\n{page_text}\n"
            pages.append(section)
            current_length += len(section)
            if current_length >= MAX_DOCUMENT_CHARS:
                break

        return "\n".join(pages)[:MAX_DOCUMENT_CHARS]
    except Exception as error:
        return f"PDF 읽기 실패: {error}"


TOOLS = [
    _tool_schema("create_excel_report", "Excel(.xlsx) 보고서를 저장합니다.", REPORT_PROPERTIES),
    _tool_schema("create_word_report", "Word(.docx) 보고서를 저장합니다.", REPORT_PROPERTIES),
    _tool_schema("create_pdf_report", "PDF(.pdf) 보고서를 저장합니다.", REPORT_PROPERTIES),
    _tool_schema("read_excel_file", "Excel(.xlsx) 내용을 읽습니다.", FILE_PROPERTY),
    _tool_schema("read_word_file", "Word(.docx) 내용을 읽습니다.", FILE_PROPERTY),
    _tool_schema("read_pdf_file", "PDF(.pdf) 텍스트를 추출합니다.", FILE_PROPERTY),
]

TOOL_FUNCTIONS = {
    "create_excel_report": create_excel_report,
    "create_word_report": create_word_report,
    "create_pdf_report": create_pdf_report,
    "read_excel_file": read_excel_file,
    "read_word_file": read_word_file,
    "read_pdf_file": read_pdf_file,
}


def ask_agent(
    client,
    question: str,
    history: list[dict[str, str]] | None = None,
    model: str = "gpt-4o",
    temperature: float = 0.1,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful AI Agent. Answer in Korean when the user uses Korean. "
                "Use a read tool first when the user asks to summarize an Excel, Word, or PDF file. "
                "After receiving extracted text, summarize it clearly and accurately."
            ),
        }
    ] + (history or []) + [{"role": "user", "content": question}]

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        if response_message.tool_calls:
            messages.append(response_message)

            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function = TOOL_FUNCTIONS.get(function_name)
                if function is None:
                    tool_result = f"지원하지 않는 도구입니다: {function_name}"
                else:
                    tool_result = function(**json.loads(tool_call.function.arguments))

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

            final_response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
            )
            return (final_response.choices[0].message.content or "").strip()

        return (response_message.content or "").strip()
    except Exception as error:
        return f"오류가 발생했습니다: {error}"


def run_chat_loop(client) -> None:
    print("\n[AI Agent 작동 시작]")
    print("예시: 'paper.pdf 논문의 핵심 내용을 요약해줘'")
    print("예시: '요약 내용을 summary.xlsx 파일로 저장해줘'")
    print("지원 형식: .xlsx, .docx, .pdf")
    print("종료: 'q' 또는 'quit'\n")

    history: list[dict[str, str]] = []

    while True:
        question = input("\n사용자: ").strip()
        if question.lower() in ("q", "quit", "exit"):
            print("프로그램을 종료합니다.")
            break

        answer = ask_agent(client, question, history=history)
        print(f"\nAI Agent: {answer}")
        print("-" * 60)

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    client = get_client()
    run_chat_loop(client)