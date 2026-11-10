# integrated_agent/tools/time_tools.py
"""지역별 현재 날짜와 시간을 조회하는 LangChain 도구."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

from langchain_core.tools import tool


TIMEZONE_ALIASES = {
    "한국": "Asia/Seoul",
    "대한민국": "Asia/Seoul",
    "서울": "Asia/Seoul",
    "seoul": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "일본": "Asia/Tokyo",
    "도쿄": "Asia/Tokyo",
    "중국": "Asia/Shanghai",
    "베이징": "Asia/Shanghai",
    "상하이": "Asia/Shanghai",
    "미국": "America/New_York",
    "뉴욕": "America/New_York",
    "시카고": "America/Chicago",
    "덴버": "America/Denver",
    "로스앤젤레스": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "영국": "Europe/London",
    "런던": "Europe/London",
    "프랑스": "Europe/Paris",
    "파리": "Europe/Paris",
    "독일": "Europe/Berlin",
    "베를린": "Europe/Berlin",
    "캐나다": "America/Toronto",
    "토론토": "America/Toronto",
    "호주": "Australia/Sydney",
    "시드니": "Australia/Sydney",
    "싱가포르": "Asia/Singapore",
    "홍콩": "Asia/Hong_Kong",
    "방콕": "Asia/Bangkok",
    "utc": "UTC",
}

COUNTRY_NOTES = {
    "미국": "미국에는 여러 시간대가 있으며 뉴욕을 기준으로 조회했습니다.",
    "캐나다": "캐나다에는 여러 시간대가 있으며 토론토를 기준으로 조회했습니다.",
    "호주": "호주에는 여러 시간대가 있으며 시드니를 기준으로 조회했습니다.",
}


@tool
def get_current_time(timezone: str) -> str:
    """지역 또는 IANA 시간대의 현재 날짜와 시간을 조회한다.

    예: 한국, 서울, 뉴욕, Asia/Seoul, America/New_York.
    지역이 불분명하면 사용자에게 먼저 확인한다.
    미국·캐나다·호주는 각각 뉴욕·토론토·시드니 기준이다.
    """
    value = timezone.strip()

    if not value:
        return json.dumps(
            {"오류": "조회할 지역이나 시간대를 입력해주세요."},
            ensure_ascii=False,
        )

    timezone_name = TIMEZONE_ALIASES.get(value.lower(), value)

    try:
        now = datetime.now(ZoneInfo(timezone_name))

    except (ZoneInfoNotFoundError, ValueError):
        return json.dumps(
            {
                "오류": "시간대를 찾지 못했습니다.",
                "입력값": value,
                "안내": (
                    "Asia/Seoul 같은 시간대를 확인해주세요. "
                    "올바른 시간대도 실패하면 tzdata 설치 여부를 확인하세요."
                ),
            },
            ensure_ascii=False,
        )

    result = {
        "요청 지역": value,
        "시간대": timezone_name,
        "현재 날짜와 시간": now.isoformat(timespec="seconds"),
        "날짜": now.strftime("%Y-%m-%d"),
        "시간": now.strftime("%H:%M:%S"),
    }

    if value in COUNTRY_NOTES:
        result["기준 안내"] = COUNTRY_NOTES[value]

    return json.dumps(result, ensure_ascii=False)


if __name__ == "__main__":
    print(get_current_time.invoke({"timezone": "서울"}))
    print(get_current_time.invoke({"timezone": "뉴욕"}))