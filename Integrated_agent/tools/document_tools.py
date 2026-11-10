# integrated_agent/tools/document_tools.py
"""문서 읽기와 TXT·Word·Excel·PDF 보고서 생성."""

import csv
import json
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

from langchain_core.tools import tool

from file_utils import (
    resolve_input_file,
    make_output_path,
    file_result,
)


def to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def extract_document(
    path: Path,
    header_points: int = 0,
    footer_points: int = 0,
) -> str:
    """파일 형식별로 텍스트를 추출한다."""
    extension = path.suffix.lower()

    if extension == ".txt":
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="cp949")

    if extension == ".pdf":
        import pymupdf

        sections = []

        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError(
                    "암호로 보호된 PDF입니다. 암호를 해제한 파일을 올려주세요."
                )

            for number, page in enumerate(document, start=1):
                rect = page.rect

                if header_points + footer_points >= rect.height:
                    raise ValueError(
                        "제외할 머리말·꼬리말 높이가 페이지보다 큽니다."
                    )

                clip = pymupdf.Rect(
                    rect.x0,
                    rect.y0 + header_points,
                    rect.x1,
                    rect.y1 - footer_points,
                )

                text = page.get_text(
                    "text",
                    clip=clip,
                    sort=True,
                ).strip()

                sections.append(
                    f"[페이지 {number}]\n"
                    + (
                        text
                        if text
                        else "[추출 가능한 텍스트 없음: 이미지 PDF일 수 있음]"
                    )
                )

        return "\n\n".join(sections)

    if extension == ".docx":
        from docx import Document
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        document = Document(path)
        sections = []

        # 본문의 문단과 표를 문서 순서대로 읽는다.
        for element in document.element.body.iterchildren():
            if element.tag == qn("w:p"):
                text = Paragraph(element, document).text.strip()

                if text:
                    sections.append(text)

            elif element.tag == qn("w:tbl"):
                table = Table(element, document)
                rows = [
                    " | ".join(
                        cell.text.replace("\n", " / ")
                        for cell in row.cells
                    )
                    for row in table.rows
                ]

                sections.append("[표]\n" + "\n".join(rows))

        return "\n\n".join(sections)

    if extension == ".xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(
            path,
            read_only=True,
            data_only=True,
        )
        sections = []

        try:
            for sheet in workbook.worksheets:
                rows = []

                for row in sheet.iter_rows(values_only=True):
                    if all(value is None for value in row):
                        continue

                    rows.append(
                        " | ".join(
                            "" if value is None else str(value)
                            for value in row
                        )
                    )

                sections.append(
                    f"[시트: {sheet.title}]\n" + "\n".join(rows)
                )
        finally:
            workbook.close()

        sections.append(
            "[참고] 수식은 파일에 저장된 계산 결과를 읽습니다. "
            "계산 결과가 저장되지 않은 수식 셀은 비어 있을 수 있습니다."
        )

        return "\n\n".join(sections)

    if extension == ".csv":
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="cp949")

        # 기존 음성 인식 CSV의 | 구분자도 그대로 보존한다.
        return text

    raise ValueError(
        "지원하는 문서는 PDF, DOCX, XLSX, CSV, TXT입니다."
    )


@tool
def read_document(
    file_path: str,
    start_char: int = 0,
    max_chars: int = 20000,
    header_points: int = 0,
    footer_points: int = 0,
) -> str:
    """업로드한 문서 또는 생성한 문서를 읽는다.

    지원: PDF, DOCX, XLSX, CSV, TXT.
    긴 문서는 '다음 시작 위치'로 다시 호출하여 이어서 읽는다.
    전체 요약 시 읽지 않은 부분을 읽었다고 말하지 않는다.
    PDF 머리말·꼬리말 제외는 사용자가 요청한 경우에만 적용한다.
    제목 확인에는 머리말·꼬리말을 제외하지 않은 원문을 사용한다.
    이미지 PDF의 OCR은 이 도구에서 지원하지 않는다.
    """
    try:
        if start_char < 0:
            raise ValueError("시작 위치는 0 이상이어야 합니다.")

        if not 1 <= max_chars <= 40000:
            raise ValueError("한 번에 읽을 글자 수는 1~40000입니다.")

        if header_points < 0 or footer_points < 0:
            raise ValueError("제외할 높이는 0 이상이어야 합니다.")

        path = resolve_input_file(file_path)

        text = extract_document(
            path,
            header_points=header_points,
            footer_points=footer_points,
        )

        if not text.strip():
            raise ValueError("문서에서 텍스트를 추출하지 못했습니다.")

        if start_char >= len(text):
            raise ValueError(
                f"시작 위치가 문서 길이({len(text)}자)를 벗어났습니다."
            )

        end_char = min(start_char + max_chars, len(text))
        has_more = end_char < len(text)

        return to_json({
            "파일명": path.name,
            "전체 글자 수": len(text),
            "읽은 시작 위치": start_char,
            "읽은 끝 위치": end_char,
            "내용": text[start_char:end_char],
            "남은 내용 있음": has_more,
            "다음 시작 위치": end_char if has_more else None,
        })

    except Exception as error:
        return to_json({
            "오류": str(error),
            "오류 종류": type(error).__name__,
        })


def write_word(path: Path, title: str, content: str):
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn

    document = Document()

    normal = document.styles["Normal"]
    normal.font.name = "맑은 고딕"
    normal.font.size = Pt(11)
    normal.element.get_or_add_rPr().rFonts.set(
        qn("w:eastAsia"), "맑은 고딕"
    )

    document.add_heading(title, level=0)

    for line in content.splitlines():
        if line.startswith("### "):
            document.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            document.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            document.add_heading(line[2:], level=1)
        elif line.startswith("- "):
            document.add_paragraph(
                line[2:],
                style="List Bullet",
            )
        else:
            document.add_paragraph(line)

    document.save(path)


def write_excel(path: Path, title: str, content: str):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "보고서"
    sheet.append(["제목", "내용"])

    # Excel 셀 길이 제한을 피하도록 본문을 나누어 저장한다.
    pieces = [
        content[index:index + 30000]
        for index in range(0, len(content), 30000)
    ]

    for index, piece in enumerate(pieces, start=1):
        sheet.append([
            title if index == 1 else f"{title} ({index})",
            piece,
        ])

    for row in sheet.iter_rows():
        for cell in row:
            # =로 시작하는 내용도 수식이 아닌 텍스트로 저장한다.
            cell.data_type = "s"
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True,
            )

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 100
    sheet.freeze_panes = "A2"

    workbook.save(path)
    workbook.close()


def write_pdf(path: Path, title: str, content: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
    )

    from config import BASE_DIR

    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        BASE_DIR / "fonts" / "NanumGothic.ttf",
    ]

    font_path = next(
        (candidate for candidate in candidates if candidate.is_file()),
        None,
    )

    if font_path is None:
        raise ValueError(
            "한글 PDF 글꼴이 없습니다. Windows 맑은 고딕 또는 "
            "integrated_agent/fonts/NanumGothic.ttf가 필요합니다."
        )

    font_name = "AgentKorean"

    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont(font_name, str(font_path))
        )

    title_style = ParagraphStyle(
        "AgentTitle",
        fontName=font_name,
        fontSize=18,
        leading=26,
        spaceAfter=18,
        wordWrap="CJK",
    )

    body_style = ParagraphStyle(
        "AgentBody",
        fontName=font_name,
        fontSize=10,
        leading=16,
        wordWrap="CJK",
        splitLongWords=True,
    )

    story = [
        Paragraph(escape(title), title_style)
    ]

    for line in content.splitlines():
        if line.strip():
            story.append(
                Paragraph(escape(line), body_style)
            )
        else:
            story.append(Spacer(1, 8))

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    document.build(story)


@tool
def create_report(
    title: str,
    content: str,
    file_format: Literal["txt", "docx", "xlsx", "pdf"] = "docx",
    filename: str = "report",
) -> str:
    """작성한 내용을 TXT, Word, Excel 또는 PDF 보고서로 저장한다.

    파일을 읽고 요약하여 저장하려면 먼저 read_document로 읽는다.
    content에는 저장할 최종 본문 전체를 전달한다.
    본문은 일반 텍스트를 기본으로 하고 Word는 제목과 목록을 지원한다.
    Excel은 제목·내용 두 열로 저장한다.
    반환된 파일 경로는 다운로드 표시에 사용한다.
    """
    path = None

    try:
        if not title.strip():
            raise ValueError("제목을 입력해주세요.")

        if not content.strip():
            raise ValueError("저장할 본문이 비어 있습니다.")

        if len(title) > 200:
            raise ValueError("제목은 200자 이내로 입력해주세요.")

        if file_format not in {"txt", "docx", "xlsx", "pdf"}:
            raise ValueError("지원하지 않는 보고서 형식입니다.")

        path = make_output_path(filename, file_format)

        if file_format == "txt":
            path.write_text(
                title + "\n\n" + content,
                encoding="utf-8",
            )
        elif file_format == "docx":
            write_word(path, title, content)
        elif file_format == "xlsx":
            write_excel(path, title, content)
        else:
            write_pdf(path, title, content)

        return to_json({
            "성공": True,
            **file_result(path),
        })

    except Exception as error:
        # 생성에 실패한 불완전한 파일만 정리한다.
        if path is not None and path.is_file():
            path.unlink(missing_ok=True)

        return to_json({
            "성공": False,
            "오류": str(error),
            "오류 종류": type(error).__name__,
        })


DOCUMENT_TOOLS = [
    read_document,
    create_report,
]


if __name__ == "__main__":
    print("문서 도구 준비 완료!")

    for current_tool in DOCUMENT_TOOLS:
        print(f"- {current_tool.name}")

    print("실제 문서 읽기·생성은 아직 실행하지 않았습니다.")