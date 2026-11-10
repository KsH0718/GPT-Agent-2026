import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run():
    OUTPUT_DIR = BASE_DIR / "output"

    # 현재 실행 중인 파이썬 인터프리터 경로(sys.executable)를 사용
    python_cmd = sys.executable

    print("🚀 [1/3] PDF -> TXT 변환 시작...")
    subprocess.run([python_cmd, str(OUTPUT_DIR / "pdf_to_txt.py")], check=True)

    print("\n🚀 [2/3] 헤더/푸터 제거 전처리 시작...")
    subprocess.run(
        [python_cmd, str(OUTPUT_DIR / "pdf_without_header_footer.py")],
        check=True,
    )

    print("\n🚀 [3/3] OpenAI 요약 생성 시작...")
    subprocess.run([python_cmd, str(BASE_DIR / "summary.py")], check=True)

    print("\n✅ 모든 작업이 순서대로 완료되었습니다!")


if __name__ == "__main__":
    run()
