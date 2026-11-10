# GPT Agent 2026 / Corev

Python 통합 AI 에이전트와 Flutter 클라이언트의 공개 소스 보관본입니다.

## 구성
- `Integrated_agent`: AI 에이전트, FastAPI 서버, 도구
- `flutter_app`: Flutter 클라이언트
- `Corev`: Windows 실행 관리자 및 패키징 스크립트
- `chap02`~`chap08`: 학습 예제와 노트북
- `tests`: 기존 API 테스트

## 복원 준비
1. 저장소를 clone하거나 ZIP으로 내려받습니다.
2. Python 가상환경 `venv`를 새로 만듭니다. `requirements-archive.txt`는 원래 환경의 패키지 목록이며, OS/GPU에 따라 설치 조정이 필요할 수 있습니다.
3. `.env.example`을 `.env`로 복사하고 본인의 API 키를 입력합니다. API 사용 비용은 해당 계정에 청구됩니다.
4. Flutter SDK 설치 후 `flutter_app`에서 `flutter pub get`을 실행합니다.
5. 백엔드: `Integrated_agent`에서 `python -m uvicorn server:app --host 127.0.0.1 --port 8000` 실행.
6. 클라이언트: `flutter_app`에서 `flutter run -d chrome` 실행.
7. 음성 기능은 별도 FFmpeg 설치와 `FFMPEG_EXE` 설정이 필요합니다.

기존 상세 안내는 `README.txt`와 `Corev/README.md`를 참고하세요. 과거 로컬 경로가 포함된 예제는 사용 환경에 맞게 바꿔야 합니다.

## 보관 범위와 검증 한계
이 저장소는 전체 디스크 백업이 아닙니다. API 키, `.env`, 대화 DB, 업로드 파일, 생성 결과, 개인 보고서, 음성 자료, 가상환경, FFmpeg 바이너리, 빌드·제출 복사본은 제외했습니다. 노트북 실행 결과와 메타데이터를 제거하고 일부 개인 경로를 익명화했습니다.

소스 구문과 업로드 파일 일치 여부를 확인합니다. 새 PC에서 패키지 설치, AI 응답, 음성 인식, Flutter/Android 실행은 이번 보관 작업에서 검증하지 않았습니다. 개인 자료가 필요하면 원본을 별도로 백업한 후 정리하세요.
