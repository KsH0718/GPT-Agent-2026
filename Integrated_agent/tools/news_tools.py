# integrated_agent/tools/news_tools.py
"""NAVER API HUB 뉴스 검색 도구."""

from usage_tracking import record_usage

import json
import re
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from config import (
    NAVER_CLIENT_ID,
    NAVER_CLIENT_SECRET,
    NAVER_NEWS_ENDPOINT,
)


def clean_news_text(value) -> str:
    """HTML 태그와 불필요한 공백을 제거한다."""
    text = re.sub(r"<[^>]*>", "", str(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def is_naver_news_url(url: str) -> bool:
    """네이버 뉴스 주소인지 확인한다."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()

        domains = (
            "news.naver.com",
            "sports.naver.com",
            "entertain.naver.com",
        )

        return (
            parsed.scheme in ("http", "https")
            and not parsed.username
            and not parsed.password
            and any(
                host == domain or host.endswith("." + domain)
                for domain in domains
            )
        )
    except ValueError:
        return False


def format_news_date(value) -> str:
    """기사 제공 시각을 한국 시간으로 표시한다."""
    if not value:
        return "시각 정보 없음"

    try:
        date = parsedate_to_datetime(str(value))

        if date.tzinfo is None:
            return str(value)

        return date.astimezone(
            timezone(timedelta(hours=9))
        ).strftime("%Y-%m-%d %H:%M:%S KST")

    except (TypeError, ValueError, OverflowError):
        return str(value)


def fetch_naver_news(query: str, count: int = 5) -> dict:
    """최대 300개 검색 결과에서 네이버 뉴스 링크를 선별한다."""
    query = str(query or "").strip()

    if not query:
        return {"오류": "검색어를 입력해주세요."}

    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {
            "오류": (
                "네이버 인증 설정이 없습니다. "
                ".env의 NAVER_CLIENT_ID와 "
                "NAVER_CLIENT_SECRET을 확인해주세요."
            )
        }

    try:
        count = max(1, min(int(count), 10))
    except (TypeError, ValueError):
        count = 5

    articles = []
    seen = set()
    checked = 0
    partial_error = None

    for start in (1, 101, 201):
        params = urlencode({
            "query": query,
            "display": 100,
            "start": start,
            "sort": "date",
            "format": "json",
        })

        request = Request(
            NAVER_NEWS_ENDPOINT + "?" + params,
            headers={
                "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
                "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET,
                "Accept": "application/json",
            },
            method="GET",
        )

        record_usage("NAVER API HUB", "뉴스 검색", f"검색 요청 start={start}",
                     note="HTTP 요청 시도 1회 · 토큰 과금 정보 없음 · 실패 포함")
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )

        except HTTPError as error:
            descriptions = {
                400: "검색어와 요청 설정을 확인해주세요.",
                401: "Client ID와 Client Secret을 확인해주세요.",
                403: "검색 API 이용 설정과 접근 제한을 확인해주세요.",
                404: "API 요청 주소를 찾지 못했습니다.",
                429: "API 요청 한도를 초과했습니다.",
            }
            partial_error = (
                f"HTTP {error.code}: "
                + descriptions.get(
                    error.code, "뉴스 API 요청에 실패했습니다."
                )
            )
            error.close()
            break

        except (URLError, TimeoutError, OSError):
            partial_error = "NAVER API HUB에 연결하지 못했습니다."
            break

        except (json.JSONDecodeError, UnicodeDecodeError):
            partial_error = "뉴스 API 응답을 해석하지 못했습니다."
            break

        if not isinstance(payload, dict):
            partial_error = "뉴스 API 응답 형식이 예상과 다릅니다."
            break

        items = payload.get("items")

        if not isinstance(items, list):
            partial_error = "뉴스 API 응답에 기사 목록이 없습니다."
            break

        for item in items:
            checked += 1

            if not isinstance(item, dict):
                continue

            link = str(item.get("link") or "").strip()

            if not is_naver_news_url(link) or link in seen:
                continue

            seen.add(link)
            articles.append({
                "제목": clean_news_text(item.get("title")),
                "요약문": clean_news_text(item.get("description")),
                "제공 시각": format_news_date(item.get("pubDate")),
                "네이버 뉴스 링크": link,
            })

            if len(articles) >= count:
                break

        if len(articles) >= count or len(items) < 100:
            break

    if partial_error and not articles:
        return {"오류": partial_error}

    result = {
        "검색 서비스": "NAVER API HUB",
        "검색어": query,
        "정렬": "최신순",
        "검사한 검색 결과 수": checked,
        "반환 기사 수": len(articles),
        "뉴스": articles,
        "참고": (
            "제목과 검색 요약문 기반이며 기사 본문 전체를 "
            "읽은 결과는 아닙니다. 최대 300개 검색 결과에서 "
            "네이버 뉴스 링크를 선별하므로 요청한 개수보다 "
            "적게 반환될 수 있습니다."
        ),
    }

    if not articles:
        result["안내"] = "조건에 맞는 네이버 뉴스를 찾지 못했습니다."

    if partial_error:
        result["안내"] = f"일부 결과만 조회했습니다. {partial_error}"

    return result


class NewsSearchInput(BaseModel):
    query: str = Field(
        min_length=1,
        description="뉴스 검색어. 예: 삼성전자, 로봇, 인공지능",
    )
    count: int = Field(
        default=5,
        ge=1,
        le=10,
        description="반환할 최대 기사 수. 1~10개",
    )


@tool(args_schema=NewsSearchInput)
def search_naver_news(query: str, count: int = 5) -> str:
    """네이버 뉴스를 최신순으로 검색한다.

    기사 제목, 검색 요약문, 제공 시각과 링크를 반환한다.
    기사 본문 전체를 조회하는 도구는 아니다.
    """
    return json.dumps(
        fetch_naver_news(query=query, count=count),
        ensure_ascii=False,
    )


NEWS_TOOLS = [search_naver_news]


if __name__ == "__main__":
    print("네이버 뉴스 도구 준비 완료!")
    print(
        "인증 설정:",
        "설정됨"
        if NAVER_CLIENT_ID and NAVER_CLIENT_SECRET
        else "찾지 못함",
    )
    print("이 확인에서는 실제 뉴스 검색을 실행하지 않습니다.")