#yfinance 라이브러리를 yf라는 이름으로 가져오기
#-> 주식 종목 정보와 기업 정보를 조회할 때 사용합니다.
import yfinance as yf

# json 라이브러리를 가져오기
#-> python 딕셔너리를 JSON 문자열 형태로 바꿀 때 사용합니다.
import json

# textwrap 라이브러리를 가져오기
#-> 긴 문자열을 지정한 길이마다 자동으로 줄바꿈 할 때 사용합니다.
import textwrap

# Microsoft(MSFT) 종목에 대한 Ticker 객체를 생성
msft = yf.Ticker("MSFT")

# 종목의 상세 정보를 딕셔너리 형태로 가져옵니다.
info = msft.info

# 파이썬 딕셔너리(info)를 JSON 문자열로 변환합니다.
json_text = json.dumps(
    info,                # json으로 바꿀 원본 데이터
    indent=4,            # 들여쓰기 수준을 4로 설정하여 가독성을 높입니다.
    ensure_ascii=False,  # 한글이 깨지지 않도록 설정합니다.
    default=str,         # 직렬화할 수 없는 객체를 문자열로 변환합니다.
)

# Json 문자열을 줄 단위로 나눕니다.
lines = json_text.splitlines()

# 각 줄을 검사하면서, 60자를 넘으면 자동 줄바꿈해서 출력합니다.
for line in lines:
    wrapped_lines = textwrap.wrap(
        line,
        width=60,  # 한 줄의 최대 길이를 60자로 설정합니다.
        replace_whitespace=False,  # 공백을 제거하지 않고 그대로 유지합니다.
        drop_whitespace=False,     # 줄 끝의 공백을 제거하지 않고 그대로 유지합니다.
    )

# 빈 줄은 wrap 결과가 []가 될 수 있으므로 따로 처리
    if not wrapped_lines:
        print()
    else:
        for wrapped_line in wrapped_lines:
            print(wrapped_line)