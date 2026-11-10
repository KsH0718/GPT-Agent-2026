# gpt_functions.py
# 시간·종목 정보·주가·애널리스트 투자의견·한 달 비교 도구

from datetime import datetime
import json
import math

import pandas as pd
import pytz
import yfinance as yf


# =========================================================
# 1. 지역명과 시간대 연결
# =========================================================

TIMEZONE_MAP = {
    "한국": "Asia/Seoul",
    "서울": "Asia/Seoul",
    "대한민국": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "seoul": "Asia/Seoul",

    "일본": "Asia/Tokyo",
    "도쿄": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",

    "중국": "Asia/Shanghai",
    "베이징": "Asia/Shanghai",
    "상하이": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "shanghai": "Asia/Shanghai",
    "china": "Asia/Shanghai",

    "홍콩": "Asia/Hong_Kong",
    "hong kong": "Asia/Hong_Kong",

    "태국": "Asia/Bangkok",
    "방콕": "Asia/Bangkok",
    "thailand": "Asia/Bangkok",
    "bangkok": "Asia/Bangkok",

    "싱가포르": "Asia/Singapore",
    "singapore": "Asia/Singapore",

    "영국": "Europe/London",
    "런던": "Europe/London",
    "uk": "Europe/London",
    "london": "Europe/London",

    "프랑스": "Europe/Paris",
    "파리": "Europe/Paris",
    "france": "Europe/Paris",
    "paris": "Europe/Paris",

    "독일": "Europe/Berlin",
    "베를린": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "berlin": "Europe/Berlin",

    "미국": "America/New_York",
    "뉴욕": "America/New_York",
    "워싱턴": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "new york": "America/New_York",
    "washington": "America/New_York",

    "시카고": "America/Chicago",
    "chicago": "America/Chicago",

    "덴버": "America/Denver",
    "denver": "America/Denver",

    "로스앤젤레스": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",

    "캐나다": "America/Toronto",
    "토론토": "America/Toronto",
    "canada": "America/Toronto",
    "toronto": "America/Toronto",

    "호주": "Australia/Sydney",
    "시드니": "Australia/Sydney",
    "australia": "Australia/Sydney",
    "sydney": "Australia/Sydney",

    "utc": "UTC",
    "gmt": "Etc/GMT",
}

IANA_TIMEZONE_MAP = {
    name.lower(): name for name in pytz.all_timezones
}


def normalize_timezone(timezone: str | None) -> str:
    """지역명 또는 IANA 시간대 이름을 정리한다."""
    cleaned = (timezone or "").strip()

    if not cleaned:
        return "Asia/Seoul"

    lowered = cleaned.lower()

    return TIMEZONE_MAP.get(
        lowered,
        IANA_TIMEZONE_MAP.get(lowered, cleaned),
    )


def get_current_time(timezone: str | None = "Asia/Seoul") -> str:
    """기존 코드와 동일하게 시간 문자열을 반환한다."""
    timezone_name = normalize_timezone(timezone)

    try:
        now = datetime.now(pytz.timezone(timezone_name))
    except pytz.UnknownTimeZoneError:
        return (
            f"오류: '{timezone_name}' 시간대를 찾을 수 없습니다. "
            "한국, 뉴욕 또는 Asia/Seoul처럼 입력하세요."
        )

    return (
        f"{now.strftime('%Y-%m-%d %H:%M:%S')} "
        f"({timezone_name}, UTC{now.strftime('%z')})"
    )


# =========================================================
# 2. 주식 조회 공통 설정
# =========================================================

STOCK_NAMES = {
    "테슬라": "TSLA",
    "tesla": "TSLA",
    "애플": "AAPL",
    "apple": "AAPL",
    "마이크로소프트": "MSFT",
    "microsoft": "MSFT",
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "아마존": "AMZN",
    "amazon": "AMZN",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "google": "GOOGL",
    "메타": "META",
    "meta": "META",
    "삼성전자": "005930.KS",
    "sk하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "네이버": "035420.KS",
    "naver": "035420.KS",
    "카카오": "035720.KS",
}

PRICE_COLUMNS = {
    "Open": "시가",
    "High": "고가",
    "Low": "저가",
    "Close": "종가",
    "Adj Close": "수정 종가",
    "Volume": "거래량",
    "Dividends": "배당금",
    "Stock Splits": "주식 분할",
    "Capital Gains": "자본이득 분배금",
}

RECOMMENDATION_COLUMNS = {
    "period": "기간",
    "strongBuy": "적극 매수",
    "buy": "매수",
    "hold": "보유",
    "sell": "매도",
    "strongSell": "적극 매도",
}

ALLOWED_PERIODS = ["5d", "1mo", "3mo", "6mo", "1y"]


def normalize_ticker(ticker: str) -> str:
    """등록된 회사명은 종목 코드로 바꾼다."""
    value = str(ticker or "").strip()
    key = value.lower().replace(" ", "")
    return STOCK_NAMES.get(key, value.upper())


def dataframe_records(frame: pd.DataFrame) -> list:
    """결측값을 포함한 표를 JSON 호환 목록으로 변환한다."""
    return json.loads(
        frame.to_json(
            orient="records",
            force_ascii=False,
            date_format="iso",
        )
    )


def price_table(history: pd.DataFrame) -> pd.DataFrame:
    """주가 표의 열 이름과 날짜를 정리한다."""
    frame = history.rename(columns=PRICE_COLUMNS).copy()
    frame.index = frame.index.strftime("%Y-%m-%d")
    frame.index.name = "날짜"
    return frame.reset_index()


def get_currency(stock) -> str:
    """확인되지 않는 통화는 추측하지 않는다."""
    try:
        return stock.fast_info["currency"] or "정보 없음"
    except Exception:
        return "정보 없음"


def error_result(message: str, error: Exception) -> dict:
    return {
        "오류": message,
        "오류 종류": type(error).__name__,
    }


# =========================================================
# 3. 회사명으로 종목 검색
# =========================================================

def search_yf_stock(query: str) -> dict:
    query = str(query or "").strip()

    if not query:
        return {"오류": "회사명 또는 종목 코드를 입력하세요."}

    known = STOCK_NAMES.get(query.lower().replace(" ", ""))

    if known:
        return {
            "검색어": query,
            "종목 후보": [
                {"종목 코드": known, "회사명": query}
            ],
        }

    try:
        quotes = yf.Search(
            query,
            max_results=5,
            news_count=0,
        ).quotes

        candidates = [
            {
                "종목 코드": item.get("symbol"),
                "회사명": item.get("longname") or item.get("shortname"),
                "거래소": item.get("exchange"),
                "종류": item.get("quoteType"),
            }
            for item in quotes
            if item.get("symbol")
        ]

        return {
            "검색어": query,
            "종목 후보": candidates,
            "참고": (
                "후보가 여러 개이면 회사명과 거래소를 확인하세요. "
                "검색되지 않으면 영문 회사명이나 정확한 종목 코드를 사용하세요."
            ),
        }

    except Exception as error:
        return error_result("종목 검색에 실패했습니다.", error)


# =========================================================
# 4. 종목 기본 정보
# =========================================================

def get_yf_stock_info(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return {"오류": "종목 코드를 입력하세요."}

    try:
        info = yf.Ticker(ticker).info

        if not info:
            return {"오류": f"{ticker}의 종목 정보가 없습니다."}

        price = info.get("currentPrice")

        if price is None:
            price = info.get("regularMarketPrice")

        return {
            "종목 코드": ticker,
            "회사명": info.get("longName") or info.get("shortName"),
            "거래소": info.get("exchange"),
            "통화": info.get("currency"),
            "최근 제공 가격": price,
            "정규장 가격 기준 시각(Unix)": info.get("regularMarketTime"),
            "전일 종가": info.get("previousClose"),
            "시가총액": info.get("marketCap"),
            "업종": info.get("industry"),
            "52주 최고가": info.get("fiftyTwoWeekHigh"),
            "52주 최저가": info.get("fiftyTwoWeekLow"),
            "참고": (
                "가격은 지연될 수 있습니다. "
                "제공되지 않는 항목은 None입니다."
            ),
        }

    except Exception as error:
        return error_result(f"{ticker} 종목 정보 조회 실패", error)


# =========================================================
# 5. 기간별 주가 조회
# =========================================================

def get_yf_stock_history(
    ticker: str,
    period: str = "5d",
) -> dict:
    """
    period:
        5d  = 최근 5거래일
        1mo = 최근 1개월
        3mo = 최근 3개월
        6mo = 최근 6개월
        1y  = 최근 1년
    """
    ticker = normalize_ticker(ticker)

    if not ticker:
        return {"오류": "종목 코드를 입력하세요."}

    if period not in ALLOWED_PERIODS:
        return {
            "오류": "기간은 5d, 1mo, 3mo, 6mo, 1y 중 선택하세요."
        }

    try:
        stock = yf.Ticker(ticker)

        history = stock.history(
            period=period,
            interval="1d",
            auto_adjust=False,
            actions=True,
        )

        if history is None or history.empty:
            return {"오류": f"{ticker}의 주가 데이터가 없습니다."}

        table = price_table(history)

        return {
            "종목 코드": ticker,
            "통화": get_currency(stock),
            "기간": period,
            "주가": dataframe_records(table),
            # pandas의 to_markdown()에서 tabulate를 사용한다.
            "마크다운 표": table.to_markdown(
                index=False,
                floatfmt=".2f",
            ),
            "참고": (
                "날짜는 거래소 현지 날짜입니다. "
                "당일 데이터는 장중 미완성일 수 있습니다. "
                "수정 종가는 배당·분할 등의 조정을 반영한 값입니다."
            ),
        }

    except Exception as error:
        return error_result(f"{ticker} 주가 조회 실패", error)


# =========================================================
# 6. 애널리스트 투자의견
# =========================================================

def get_yf_stock_recommendations(ticker: str) -> dict:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return {"오류": "종목 코드를 입력하세요."}

    try:
        recommendations = yf.Ticker(ticker).recommendations

        if recommendations is None or recommendations.empty:
            return {
                "종목 코드": ticker,
                "안내": "제공되는 애널리스트 투자의견이 없습니다.",
            }

        table = recommendations.rename(
            columns=RECOMMENDATION_COLUMNS
        ).copy()

        return {
            "종목 코드": ticker,
            "기간 설명": "0m은 현재 집계, -1m은 1개월 전 집계입니다.",
            "투자의견": dataframe_records(table),
            "마크다운 표": table.to_markdown(index=False),
            "참고": (
                "각 값은 투자의견별 애널리스트 수입니다. "
                "개별 분석 보고서 원문이 아닌 집계 정보입니다."
            ),
        }

    except Exception as error:
        return error_result(f"{ticker} 투자의견 조회 실패", error)


def get_yf_recommendations(ticker: str) -> dict:
    """기존 노트북·Streamlit 코드의 함수 이름도 사용할 수 있다."""
    return get_yf_stock_recommendations(ticker)


# =========================================================
# 7. 한 달 전 주가 비교
# =========================================================

def compare_yf_stock_month(ticker: str) -> dict:
    """
    거래소 현지 오늘보다 이전인 최근 거래일을 기준으로 비교한다.
    한 달 전이 휴장일이면 그 이전의 가장 가까운 거래일을 사용한다.
    """
    ticker = normalize_ticker(ticker)

    if not ticker:
        return {"오류": "종목 코드를 입력하세요."}

    try:
        stock = yf.Ticker(ticker)

        history = stock.history(
            period="3mo",
            interval="1d",
            auto_adjust=False,
            actions=True,
        )

        if history is None or history.empty:
            return {"오류": f"{ticker}의 비교용 주가 데이터가 없습니다."}

        history = history.sort_index().dropna(subset=["Close"])

        exchange_tz = history.index.tz

        if exchange_tz is None:
            return {"오류": "거래소 시간대를 확인하지 못했습니다."}

        today = pd.Timestamp.now(tz=exchange_tz).date()

        # 당일 데이터는 장중인지 확정 종가인지 혼동하지 않도록 제외한다.
        history = history[
            [date < today for date in history.index.date]
        ]

        if history.empty:
            return {"오류": "당일 이전 거래일 데이터가 없습니다."}

        latest_date = history.index[-1]

        # 달력 기준 한 달 전. 30일 전과는 다를 수 있다.
        target_date = latest_date - pd.DateOffset(months=1)
        previous_history = history.loc[history.index <= target_date]

        if previous_history.empty:
            return {
                "오류": (
                    "한 달 전 비교에 필요한 데이터가 없습니다. "
                    "신규 상장 또는 데이터 누락 여부를 확인하세요."
                )
            }

        previous_date = previous_history.index[-1]

        # 오래된 데이터로 현재 상태를 단정하지 않는다.
        if (today - latest_date.date()).days > 10:
            return {
                "오류": (
                    "최근 거래 데이터가 10일 넘게 갱신되지 않았습니다. "
                    "거래정지 또는 데이터 누락 여부를 확인하세요."
                )
            }

        if (target_date.date() - previous_date.date()).days > 10:
            return {
                "오류": (
                    "한 달 전 기준일 부근의 거래 데이터가 부족합니다. "
                    "정상적인 한 달 비교를 수행하기 어렵습니다."
                )
            }

        previous_row = history.loc[previous_date]
        latest_row = history.loc[latest_date]

        old_close = float(previous_row["Close"])
        new_close = float(latest_row["Close"])

        if (
            not math.isfinite(old_close)
            or not math.isfinite(new_close)
            or old_close <= 0
        ):
            return {"오류": "비교에 필요한 종가가 유효하지 않습니다."}

        change = new_close - old_close
        change_pct = change / old_close * 100

        selected = history.loc[[previous_date, latest_date]]
        table = price_table(selected)
        table.insert(0, "구분", ["한 달 전 기준", "최근 기준"])

        if change > 0:
            status = "상승"
        elif change < 0:
            status = "하락"
        else:
            status = "보합"

        result = {
            "종목 코드": ticker,
            "통화": get_currency(stock),
            "거래소 시간대": str(exchange_tz),
            "한 달 전 목표일": target_date.strftime("%Y-%m-%d"),
            "실제 이전 거래일": previous_date.strftime("%Y-%m-%d"),
            "실제 최근 거래일": latest_date.strftime("%Y-%m-%d"),
            "이전 종가": old_close,
            "최근 종가": new_close,
            "종가 차이": round(change, 4),
            "종가 변동률(%)": round(change_pct, 2),
            "가격 상태": status,
            "비교표": dataframe_records(table),
            "마크다운 표": table.to_markdown(
                index=False,
                floatfmt=".2f",
            ),
            "참고": (
                "당일 데이터는 제외했습니다. "
                "최근 기준 거래일의 달력상 한 달 전 또는 직전 거래일과 비교합니다. "
                "종가 변화는 배당을 포함한 총수익률과 다릅니다. "
                "가격 변화만으로 상승·하락 원인이나 미래 수익을 단정할 수 없습니다."
            ),
        }

        if "Adj Close" in history.columns:
            old_adjusted = float(previous_row["Adj Close"])
            new_adjusted = float(latest_row["Adj Close"])

            if (
                math.isfinite(old_adjusted)
                and math.isfinite(new_adjusted)
                and old_adjusted > 0
            ):
                result["수정 종가 변동률(%)"] = round(
                    (new_adjusted / old_adjusted - 1) * 100,
                    2,
                )

        interval = history.loc[
            (history.index > previous_date)
            & (history.index <= latest_date)
        ]

        events = []

        for date, row in interval.iterrows():
            dividend = row.get("Dividends", 0)
            split = row.get("Stock Splits", 0)

            has_dividend = pd.notna(dividend) and dividend != 0
            has_split = pd.notna(split) and split != 0

            if has_dividend or has_split:
                events.append({
                    "날짜": date.strftime("%Y-%m-%d"),
                    "배당금": float(dividend) if has_dividend else 0,
                    "주식 분할": float(split) if has_split else 0,
                })

        result["비교 구간 배당·분할"] = events
        return result

    except Exception as error:
        return error_result(f"{ticker} 한 달 비교 실패", error)


# =========================================================
# 8. GPT에 전달할 함수 설명
# =========================================================

def make_tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TICKER_PROPERTY = {
    "type": "string",
    "description": (
        "Yahoo Finance 종목 코드. "
        "예: 테슬라 TSLA, 애플 AAPL, 마이크로소프트 MSFT, "
        "삼성전자 005930.KS. "
        "불확실하면 search_yf_stock으로 먼저 확인한다."
    ),
}

tools = [
    make_tool(
        "get_current_time",
        (
            "지역의 현재 날짜와 시간을 조회한다. "
            "미국은 뉴욕, 캐나다는 토론토, 호주는 시드니 기준이며 "
            "답변에 기준 도시를 명시한다."
        ),
        {
            "timezone": {
                "type": "string",
                "description": "한국, 뉴욕, Asia/Seoul 등의 지역 또는 시간대",
            }
        },
        [],
    ),
    make_tool(
        "search_yf_stock",
        (
            "회사명이나 종목 코드로 종목 후보를 검색한다. "
            "후보가 모호하면 사용자에게 회사나 거래소를 확인한다."
        ),
        {
            "query": {
                "type": "string",
                "description": "회사명 또는 종목 코드",
            }
        },
        ["query"],
    ),
    make_tool(
        "get_yf_stock_info",
        "종목의 회사명, 통화, 가격, 시가총액 등 주요 정보를 조회한다.",
        {"ticker": TICKER_PROPERTY},
        ["ticker"],
    ),
    make_tool(
        "get_yf_stock_history",
        (
            "지정 기간의 일별 시가·고가·저가·종가·거래량 등을 조회한다. "
            "기간을 생략하면 최근 5거래일이다."
        ),
        {
            "ticker": TICKER_PROPERTY,
            "period": {
                "type": "string",
                "enum": ALLOWED_PERIODS,
                "description": "5d, 1mo, 3mo, 6mo, 1y 중 선택",
            },
        },
        ["ticker"],
    ),
    make_tool(
        "get_yf_stock_recommendations",
        (
            "애널리스트 투자의견별 인원 집계를 조회한다. "
            "현재 집계와 이전 월 집계가 제공될 수 있다."
        ),
        {"ticker": TICKER_PROPERTY},
        ["ticker"],
    ),
    make_tool(
        "compare_yf_stock_month",
        (
            "최근 기준 종가와 달력 기준 한 달 전 종가를 비교한다. "
            "한 달 전과 어떤 상태인지 질문하면 이 도구를 사용한다. "
            "실제 거래일·종가 차이·변동률을 계산해서 반환한다. "
            "투자의견도 필요하면 get_yf_stock_recommendations를 함께 호출한다."
        ),
        {"ticker": TICKER_PROPERTY},
        ["ticker"],
    ),
]


# =========================================================
# 9. 함수 이름과 실제 함수 연결
# =========================================================

available_functions = {
    "get_current_time": get_current_time,
    "search_yf_stock": search_yf_stock,
    "get_yf_stock_info": get_yf_stock_info,
    "get_yf_stock_history": get_yf_stock_history,
    "get_yf_stock_recommendations": get_yf_stock_recommendations,
    "compare_yf_stock_month": compare_yf_stock_month,

    # 이전 함수 이름도 계속 사용할 수 있다.
    "get_yf_recommendations": get_yf_recommendations,
}


def execute_tool(function_name: str, arguments: str | dict) -> str:
    """GPT가 요청한 함수를 실행하고 결과를 JSON 문자열로 반환한다."""
    function = available_functions.get(function_name)

    if function is None:
        return json.dumps(
            {"오류": f"등록되지 않은 함수입니다: {function_name}"},
            ensure_ascii=False,
        )

    try:
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        if not isinstance(arguments, dict):
            raise ValueError("함수 인자는 JSON 객체여야 합니다.")

        result = function(**arguments)

        return json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )

    except Exception as error:
        return json.dumps(
            {
                "오류": "도구 실행에 실패했습니다.",
                "오류 종류": type(error).__name__,
            },
            ensure_ascii=False,
        )


# =========================================================
# 10. 기존 노트북에서 사용하는 종목 객체
# =========================================================

msft = yf.Ticker("MSFT")


# =========================================================
# 11. 파일을 직접 실행했을 때만 실행
# =========================================================

if __name__ == "__main__":
    print("한국:", get_current_time("한국"))
    print("뉴욕:", get_current_time("뉴욕"))
    print("런던:", get_current_time("런던"))

    print(f"\nGPT 도구 {len(tools)}개 준비 완료")
    print('종목 정보: get_yf_stock_info("TSLA")')
    print('최근 주가: get_yf_stock_history("TSLA", "1mo")')
    print('투자의견: get_yf_stock_recommendations("TSLA")')
    print('한 달 비교: compare_yf_stock_month("TSLA")')