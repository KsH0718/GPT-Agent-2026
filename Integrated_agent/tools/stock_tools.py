# integrated_agent/tools/stock_tools.py
"""기존 주식 조회 함수를 LangChain 도구로 연결한다."""

import json
from typing import Literal

from langchain_core.tools import tool

from . import stock_backend


def to_json(result) -> str:
    """결과를 JSON으로 변환하고 중복된 마크다운 표는 제외한다."""
    if isinstance(result, dict):
        result = dict(result)
        result.pop("마크다운 표", None)

    return json.dumps(
        result,
        ensure_ascii=False,
        default=str,
    )


@tool
def search_yf_stock(query: str) -> str:
    """회사명 또는 종목 코드로 주식 종목 후보를 검색한다.

    종목 코드가 불확실할 때 먼저 사용한다.
    후보가 여러 개이고 모호하면 사용자에게 확인한다.
    """
    return to_json(
        stock_backend.search_yf_stock(query=query)
    )


@tool
def get_yf_stock_info(ticker: str) -> str:
    """종목의 회사명, 통화, 최근 제공 가격, 시가총액 등을 조회한다.

    ticker 예: TSLA, MSFT, 005930.KS.
    제공 가격은 지연될 수 있으며 실시간 가격을 보장하지 않는다.
    """
    return to_json(
        stock_backend.get_yf_stock_info(ticker=ticker)
    )


@tool
def get_yf_stock_history(
    ticker: str,
    period: Literal["5d", "1mo", "3mo", "6mo", "1y"] = "1mo",
) -> str:
    """지정한 종목의 기간별 일별 주가를 조회한다.

    기간: 5d, 1mo, 3mo, 6mo, 1y.
    실제 조회 날짜와 통화를 확인하여 답변한다.
    당일 데이터는 장중 미완성일 수 있다.
    """
    return to_json(
        stock_backend.get_yf_stock_history(
            ticker=ticker,
            period=period,
        )
    )


@tool
def get_yf_stock_recommendations(ticker: str) -> str:
    """종목의 애널리스트 투자의견별 인원 집계를 조회한다.

    개별 보고서 원문이 아닌 집계 정보다.
    제공되는 정보가 없으면 그 사실을 사용자에게 알린다.
    """
    return to_json(
        stock_backend.get_yf_stock_recommendations(
            ticker=ticker
        )
    )


@tool
def compare_yf_stock_month(ticker: str) -> str:
    """당일 이전 최근 거래일과 달력상 한 달 전의 종가를 비교한다.

    한 달 전이 휴장일이면 그 이전의 가까운 거래일을 사용한다.
    실제 비교 거래일, 종가 차이, 변동률을 반환한다.
    당일 종가는 제외하므로 지금의 실시간 가격으로 설명하지 않는다.
    """
    return to_json(
        stock_backend.compare_yf_stock_month(
            ticker=ticker
        )
    )


STOCK_TOOLS = [
    search_yf_stock,
    get_yf_stock_info,
    get_yf_stock_history,
    get_yf_stock_recommendations,
    compare_yf_stock_month,
]


if __name__ == "__main__":
    print(f"주식 도구 {len(STOCK_TOOLS)}개 연결 완료!")

    for current_tool in STOCK_TOOLS:
        print(f"- {current_tool.name}")