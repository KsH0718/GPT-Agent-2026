# integrated_agent/config.py
"""통합 에이전트의 설정과 파일 경로."""

import os
from pathlib import Path

from dotenv import dotenv_values


# 1. 폴더 경로
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

# 필요한 저장 폴더 자동 생성
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# 2. 기존 .env 파일 읽기
# 위쪽 파일의 설정을 우선 사용한다.
ENV_CANDIDATES = [
    BASE_DIR / ".env",
    PROJECT_DIR / ".env",
    PROJECT_DIR / "chap08" / ".env",
    PROJECT_DIR / "chap07" / ".env",
    PROJECT_DIR / "chap06" / ".env",
    PROJECT_DIR / "chap05" / ".env",
    PROJECT_DIR / "chap04" / ".env",
    PROJECT_DIR / "chap02" / ".env",
]

_env_settings = [
    dotenv_values(path, encoding="utf-8-sig")
    for path in ENV_CANDIDATES
    if path.is_file()
]


def read_setting(name: str, default: str = "") -> str:
    """환경변수, .env 파일 순서로 비어 있지 않은 설정을 읽는다."""
    value = os.getenv(name)

    if value and value.strip():
        return value.strip()

    for settings in _env_settings:
        value = settings.get(name)

        if value and str(value).strip():
            return str(value).strip()

    return default


# 3. 모델과 API 설정
OPENAI_API_KEY = read_setting("OPENAI_API_KEY")
OPENAI_MODEL = read_setting("OPENAI_MODEL", "gpt-4o")

# 공식 Jev API. 키가 없어도 기존 기능은 사용할 수 있다.
TYPESAFE_API_KEY = read_setting("TYPESAFE_API_KEY")
JEV_MODEL = read_setting("JEV_MODEL", "jev-latest")

NAVER_CLIENT_ID = read_setting("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = read_setting("NAVER_CLIENT_SECRET")

NAVER_NEWS_ENDPOINT = (
    "https://naverapihub.apigw.ntruss.com/search/v1/news"
)

WHISPER_MODEL_ID = "openai/whisper-large-v3-turbo"


# 4. 기존 FFmpeg 위치
# 실제 실행 가능 여부는 음성 도구에서 확인한다.
FFMPEG_EXE = read_setting(
    "FFMPEG_EXE",
    str(PROJECT_DIR / "chap05" / "ffmpeg" / "bin" / "ffmpeg.exe"),
)


# 5. 에이전트 실행 제한
MAX_TOOL_ROUNDS = 8
MAX_TOOL_CALLS_PER_ROUND = 8
MAX_UPLOAD_MB = 100


# 6. 이 파일을 직접 실행했을 때 설정 확인
if __name__ == "__main__":
    print("통합 에이전트 설정 확인")
    print(f"프로젝트 폴더: {PROJECT_DIR}")
    print(f"업로드 폴더: {UPLOAD_DIR}")
    print(f"결과 저장 폴더: {OUTPUT_DIR}")
    print(f"사용 모델: {OPENAI_MODEL}")
    print("Jev 키:", "설정됨" if TYPESAFE_API_KEY else "찾지 못함")
    print("Jev 모델:", JEV_MODEL)

    print(
        "OpenAI 키:",
        "설정됨" if OPENAI_API_KEY else "찾지 못함",
    )

    print(
        "네이버 인증:",
        "설정됨"
        if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET
        else "찾지 못함",
    )

    print(
        "FFmpeg 파일:",
        "있음" if Path(FFMPEG_EXE).is_file() else "찾지 못함",
    )

    print("\n※ 설정됨은 키를 읽었다는 뜻이며 인증 성공 여부는 아닙니다.")