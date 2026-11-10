# 나의 AI 비서

Python 3.10 이상, 개인 PC에서 사용하는 Streamlit 챗봇입니다.
기존 chap07 파일과 충돌하지 않도록 별도 assistant_app 폴더로 구성했습니다.

## 실행 (Windows / VS Code)
1. ZIP을 풀고 assistant_app 폴더를 VS Code에서 엽니다.
2. 기존 가상환경을 활성화한 터미널에서 다음을 실행합니다.

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

3. .env의 OPENAI_API_KEY에 기존 키를 입력합니다. 키를 코드나 채팅에 붙이지 마세요.
4. 실행합니다.

```powershell
python -m streamlit run app.py --server.address 127.0.0.1
```

프로젝트 최상위 폴더에서 실행하려면 실제 압축 해제 위치에 맞춰 다음처럼 실행합니다.

```powershell
python -m streamlit run assistant_app/app.py --server.address 127.0.0.1
```

API 키를 바꾼 경우 Ctrl+C로 서버를 종료하고 다시 실행하세요.

## 뉴스 설정
https://developers.naver.com/apps/#/register 에서 애플리케이션을 등록하고 검색 API를 선택합니다.
발급된 Client ID와 Client Secret을 .env의 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET에 넣습니다.
키가 없어도 시간·날씨·일정·알람 기능은 사용할 수 있습니다.
뉴스는 기사 전문이 아닌 네이버 검색 요약문이며 원문 링크/제공 시각을 함께 표시하도록 구성했습니다.

## 질문 예시
- 서울 지금 몇 시야?
- 서울 오늘과 내일 날씨 알려줘
- 최신 임베디드 AI 뉴스 찾아줘
- 내일 오후 3시 프로젝트 회의 일정 저장해줘
- 1분 뒤에 스트레칭하라고 알람 설정해줘
- 저장된 일정과 알람 보여줘
- ID 3번 일정 삭제해줘

## 동작과 한계
- 일정/알람은 같은 폴더의 assistant.db에 저장됩니다. 프로그램을 꺼도 유지됩니다.
- schedule은 일정 저장만, alarm은 시각이 지났을 때 화면 알림을 표시합니다.
- 화면 알람은 활성 브라우저 세션에서 약 5초마다 확인합니다. 절전·탭 비활성화·접속 종료 등으로 지연될 수 있습니다.
- 소리, OS 알림, Telegram 전송, 컴퓨터가 꺼진 동안 실행은 포함하지 않습니다.
- 지난 미확인 알람은 다시 앱을 열 때 표시됩니다. 확인 버튼을 누르면 해제됩니다.
- 현재 날씨는 Open-Meteo 기상 모델 기반이고 예보는 현지 오늘부터 3일입니다.
- 도시 검색은 한글 결과가 없으면 영문으로 재검색하도록 모델에 지시합니다. 동명 도시는 국가를 함께 말해주세요.
- 기본 일정 시간대는 한국입니다. 해외는 IANA 시간대 또는 도시를 지정하세요.
- 대화는 세션 메모리에만 저장되고, 일정은 영구 저장됩니다. 새 대화는 DB를 지우지 않습니다.
- 로그인 없는 개인용입니다. 여러 사람이 접속하면 일정 DB를 공유합니다.
- OpenAI에는 대화와 도구 결과가 전송됩니다. 모델 호출 비용은 기존 API 계정에 발생합니다.
- Open-Meteo 공개 API는 비상업적 학습용 기준입니다. 상업 서비스로 전환할 때 이용 조건을 확인하세요.
- SQLite 로컬 처리와 도구 연결을 검증했으며 실제 API 인증/브라우저 통합 실행은 사용자 환경에서 확인해야 합니다.

## 출처
- Streamlit: https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
- 날씨 (CC BY 4.0): https://open-meteo.com/en/docs
- 도시 검색: https://open-meteo.com/en/docs/geocoding-api
- 네이버 뉴스: https://developers.naver.com/docs/serviceapi/search/news/news.md
- OpenAI 도구 호출: https://developers.openai.com/api/docs/guides/function-calling
