Flutter 한글 입력 표시 개선 패치

1. Flutter를 q로 종료하고 현재 main.dart, pubspec.yaml을 백업합니다.
2. 이 폴더 내용(lib, pubspec.yaml, install_font.ps1)을 기존 flutter_app 안에 복사합니다.
3. flutter_app 터미널에서 실행합니다:
   powershell -ExecutionPolicy Bypass -File .\install_font.ps1
   flutter pub get
   dart analyze
   flutter test
   flutter run -d chrome

글꼴 설치에는 인터넷이 필요합니다. 설치 성공 후에는 글꼴을 앱에 포함해 사용합니다.
Google Fonts 공식 저장소의 Noto Sans KR와 OFL 라이선스를 다운로드합니다.
기존 Enter/Shift+Enter, 한글 조합, API, 로고 및 색상 코드는 유지합니다.
실제 Chrome 재현 검증은 사용자 PC에서 필요합니다.
