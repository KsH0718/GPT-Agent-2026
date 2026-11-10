# integrated_agent/file_utils.py
"""업로드 파일 저장, 파일 경로 확인, 결과 파일명 생성."""

import re
from pathlib import Path
from uuid import uuid4

from config import UPLOAD_DIR, OUTPUT_DIR, MAX_UPLOAD_MB


ALLOWED_UPLOAD_EXTENSIONS = {
    # 문서
    ".pdf", ".docx", ".xlsx", ".csv", ".txt",
    # 이미지
    ".jpg", ".jpeg", ".png", ".webp",
    # 음성·영상: 영상은 음성 추출용
    ".mp3", ".wav", ".m4a", ".flac",
    ".ogg", ".webm", ".mp4",
}

ALLOWED_OUTPUT_EXTENSIONS = {
    ".txt", ".csv", ".docx", ".xlsx", ".pdf", ".json",
}


def safe_filename(filename: str) -> str:
    """폴더 경로와 Windows에서 사용할 수 없는 문자를 제거한다."""
    name = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")

    if not name:
        raise ValueError("파일 이름이 비어 있습니다.")

    # 긴 이름은 확장자를 유지하면서 줄인다.
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem[:100].strip(" .") or "file"

    return stem + suffix


def save_uploaded_file(uploaded_file) -> Path:
    """Streamlit UploadedFile을 uploads 폴더에 저장한다."""
    filename = safe_filename(uploaded_file.name)
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 파일 형식입니다: {extension}"
        )

    max_bytes = MAX_UPLOAD_MB * 1024 * 1024

    if uploaded_file.size > max_bytes:
        raise ValueError(
            f"파일 하나의 크기는 {MAX_UPLOAD_MB}MB 이하여야 합니다."
        )

    data = uploaded_file.getvalue()

    if not data:
        raise ValueError("빈 파일은 업로드할 수 없습니다.")

    if len(data) > max_bytes:
        raise ValueError(
            f"파일 하나의 크기는 {MAX_UPLOAD_MB}MB 이하여야 합니다."
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # 같은 이름의 파일을 다시 올려도 기존 파일을 덮어쓰지 않는다.
    stored_name = f"{uuid4().hex}_{filename}"
    path = UPLOAD_DIR / stored_name

    with path.open("xb") as file:
        file.write(data)

    return path.resolve()


def resolve_input_file(file_path: str) -> Path:
    """uploads 또는 output 안의 실제 파일인지 확인한다.

    절대 경로 또는 uploads/파일명, output/파일명을 받는다.
    파일명만 입력되면 uploads와 output에서 찾는다.
    """
    raw = str(file_path).strip()

    if not raw:
        raise ValueError("파일 경로를 입력해주세요.")

    requested = Path(raw)

    if requested.is_absolute():
        candidates = [requested]
    else:
        candidates = [
            UPLOAD_DIR.parent / requested,
            UPLOAD_DIR / requested,
            OUTPUT_DIR / requested,
        ]

    roots = [
        UPLOAD_DIR.resolve(),
        OUTPUT_DIR.resolve(),
    ]

    matches = []

    for candidate in candidates:
        resolved = candidate.resolve()

        if not any(
            resolved.is_relative_to(root)
            for root in roots
        ):
            continue

        if resolved.is_file() and resolved not in matches:
            matches.append(resolved)

    if not matches:
        raise FileNotFoundError(
            "업로드 또는 결과 폴더에서 파일을 찾지 못했습니다. "
            "화면에 등록된 파일 경로를 사용해주세요."
        )

    if len(matches) > 1:
        raise ValueError(
            "같은 이름의 파일이 여러 개입니다. "
            "uploads/파일명 또는 output/파일명으로 지정해주세요."
        )

    return matches[0]


def make_output_path(
    filename: str,
    extension: str,
) -> Path:
    """고유한 결과 파일 경로를 만든다. 실제 파일은 도구가 저장한다."""
    extension = extension.lower()

    if not extension.startswith("."):
        extension = "." + extension

    if extension not in ALLOWED_OUTPUT_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 저장 형식입니다: {extension}"
        )

    cleaned = safe_filename(filename)
    stem = Path(cleaned).stem[:80] or "result"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return (
        OUTPUT_DIR / f"{stem}_{uuid4().hex}{extension}"
    ).resolve()


def file_result(path: Path) -> dict:
    """생성된 파일의 다운로드 표시에 필요한 정보를 반환한다."""
    checked = resolve_input_file(str(path))

    return {
        "파일명": checked.name,
        "파일 경로": str(checked),
        "파일 크기(bytes)": checked.stat().st_size,
    }


if __name__ == "__main__":
    print("파일 관리 준비 완료!")
    print("업로드 폴더:", UPLOAD_DIR)
    print("결과 저장 폴더:", OUTPUT_DIR)
    print("파일당 업로드 제한:", MAX_UPLOAD_MB, "MB")