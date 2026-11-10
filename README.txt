AI Agent Flutter 통합 기능 적용 안내

이 압축파일은 기존 프로젝트에 적용할 수정 파일 모음입니다.
전체 프로젝트를 삭제하거나 새로 만들지 마세요.

1. Flutter 실행을 q로 종료하고 FastAPI 터미널은 Ctrl+C로 종료합니다.
2. 변경할 기존 파일과 Integrated_agent/data 폴더를 별도 위치에 백업합니다.
3. 압축을 푼 폴더의 Integrated_agent, flutter_app 폴더를 복사해 아래 프로젝트 폴더에 붙여넣고 같은 파일은 바꾸기를 선택합니다.

C:\Users\YOUR_USER\OneDrive\바탕 화면\GPT_AGENT_2026_STUDENT_ID

복사 후 server.py 위치:
GPT_AGENT_2026_STUDENT_ID\Integrated_agent\server.py
복사 후 main.dart 위치:
GPT_AGENT_2026_STUDENT_ID\flutter_app\lib\main.dart

기존 .env, config.py, chat_store.py, usage_tracking.py, file_utils.py,
나머지 tools 파일, data, uploads, output, android, web 폴더는 유지합니다.
file_utils.py는 이번에 전달받지 않은 파일이므로 기존 프로젝트의 파일을 사용합니다.
이번 패키지로 빈 폴더에서 새 프로젝트를 실행할 수는 없습니다.

4. FastAPI 터미널에서 추가 패키지를 설치하고 실행합니다.

cd "C:\Users\YOUR_USER\OneDrive\바탕 화면\GPT_AGENT_2026_STUDENT_ID\Integrated_agent"
& "..\venv\Scripts\python.exe" -m pip install -r requirements-flutter.txt
& "..\venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000

기존 requirements-before-whisper 파일을 다시 설치할 필요는 없습니다.
기존 GPU/Whisper 설치를 유지합니다.

5. 다른 터미널에서 Flutter 패키지를 적용합니다.

cd "C:\Users\YOUR_USER\OneDrive\바탕 화면\GPT_AGENT_2026_STUDENT_ID\flutter_app"
flutter pub get
dart analyze
flutter test
flutter run -d chrome

패키지가 추가되어 이번에는 Hot Reload 대신 완전히 다시 실행합니다.
아이콘 이미지가 이미 적용되었다면 아이콘 생성 명령은 다시 실행하지 않아도 됩니다.
build 삭제 오류가 재발하면 Flutter를 중지하고 앱용 Chrome 창을 닫은 뒤,
이전에 성공했던 방식대로 build만 수동 삭제합니다. .dart_tool 자동 삭제는 추가하지 않았습니다.

6. Android Studio 사용
- Flutter/Dart 플러그인을 설치 또는 활성화합니다.
- File > Open에서 기존 flutter_app 폴더 전체를 엽니다.
- Flutter SDK: C:\Users\YOUR_USER\src\flutter
- 실행 장치로 켜둔 에뮬레이터를 선택하고 lib/main.dart를 실행합니다.
- Android 에뮬레이터는 자동으로 http://10.0.2.2:8000에 연결됩니다.
- Chrome은 자동으로 http://127.0.0.1:8000에 연결됩니다.
- 실물 휴대폰/외부 공개 서버는 별도 네트워크 및 인증 구성이 필요합니다.

연결한 기능
- 기존 OpenAI 기반 도구 선택 및 채팅, 진행 상태와 답변 조각 수신
- 새 대화 생성, SQLite의 기존 대화 불러오기, 대화별 파일 목록
- 문서/이미지/음성 파일 첨부, 파일당 기존 MAX_UPLOAD_MB 제한
- 기존 문서 읽기/보고서 생성/이미지 분석·비교·퀴즈/Whisper/뉴스/주식/시간 도구 호출
- 생성된 보고서 및 음성 기록 파일 다운로드 (브라우저에서 열기/저장)
- Jev 강제 평가, 같은 사건 이어가기, 근거 부족 시 판단 보류 표시
- 답변별 사용량과 현재 대화/전체 저장 대화 사용량
- 네이버 뉴스 요청 시도 횟수, OpenAI 이미지 응답의 실제 usage 수집
- 로컬 Whisper 실행 기록, OpenAI 음성 응답의 음성 길이 기록
- Markdown 답변, 표 형태 도구 결과, 뉴스 링크, 답변 복사
- 조금 더 진한 하늘색 배경, Enter 전송/Shift+Enter 줄바꿈
- 글자 크기 및 출력 조각 지연 설정 (현재 앱 실행 동안 적용)

사용량의 의미
- 계정 전체의 청구액/잔액이 아닌, 이 앱에서 수집해 저장한 기록입니다.
- 입력/출력/합계는 API가 반환한 값만 표시합니다. 미수신 값을 0으로 만들지 않습니다.
- NAVER API HUB는 HTTP 요청 시도 횟수(실패 포함)를 기록하며 토큰값은 없습니다.
- 로컬 Whisper는 API 토큰 사용이 아닙니다.
- API 실패·SDK 내부 재시도·중단 시 미수신 사용량은 누락될 수 있습니다.
- 이미지/음성 토큰 수집 보완은 적용 후 새 요청부터 반영됩니다. 과거 값은 복원하지 않습니다.
- Jev 수치는 모델 추정/판정 확신도이며 검증된 정답률이 아닙니다.

연결 끊김
Flutter를 닫아도 실행 중인 서버 worker는 결과 저장을 시도합니다.
연결이 끊겼을 때 같은 요청을 바로 다시 보내지 말고, 처리가 끝난 뒤
대화 메뉴에서 해당 대화를 다시 열거나 새로고침해 결과를 확인하세요.
현재 서버는 한 번에 한 요청을 실행합니다. uvicorn의 다중 worker 옵션을 사용하지 마세요.
같은 대화를 Streamlit과 Flutter에서 동시에 수정하지 마세요.

확인 순서
1. '안녕' 전송 후 답변 및 사용량 펼치기
2. '오늘 주요 AI 뉴스 3개를 찾아줘' 전송 후 네이버 기록 확인
3. 작은 TXT 문서를 첨부하고 요약 요청
4. '이 요약을 Word 보고서로 만들어줘' 요청 후 다운로드
5. 설정의 Jev 판단을 켜고 근거와 함께 질문
6. 새 대화 생성 후 이전 대화로 돌아가 기록 확인
7. 서버를 재시작하고 대화 목록과 파일 다운로드 확인

검증 및 남은 확인
Python 문법 검사 및 API 모의 테스트 7개 통과:
대화 분리/저장, 스트림·옵션 전달·사용량, 업로드 제한·중복,
오류 후 보고서/사용량 보존, 허용 폴더 밖 다운로드 차단,
동시 요청 거부, 저장 실패 전달.
실제 유료 API 호출 및 Flutter/Android 실행 검사는 여기서 수행하지 못했습니다.
Flutter widget_test.dart에 Enter 전송/오류 복구/Shift+Enter 테스트를 포함했습니다.
기존 Streamlit의 주가 그래프는 이번 Flutter 버전에서는 표로 표시합니다.
문서 미리보기/이미지 썸네일/앱 내부 음성 녹음은 추가하지 않았습니다.

선택: Python 모의 테스트를 직접 실행하려면 tests 폴더도 프로젝트 루트에 복사합니다.
프로젝트 루트에서:
& ".\venv\Scripts\python.exe" -m pip install pytest httpx
& ".\venv\Scripts\python.exe" -m pytest tests/test_api.py -q
실제 API 키는 사용하지 않고 임시 데이터베이스로 검사합니다.
