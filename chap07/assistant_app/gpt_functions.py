"""시간·날씨·뉴스·개인 일정 도구. 개인 PC의 단일 사용자용."""
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import os, sqlite3, json, re, html
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError

DB_PATH = Path(__file__).with_name('assistant.db')
UTC = dt_timezone.utc
ALIASES = {'한국':'Asia/Seoul','서울':'Asia/Seoul','일본':'Asia/Tokyo','도쿄':'Asia/Tokyo','뉴욕':'America/New_York','런던':'Europe/London','파리':'Europe/Paris','시드니':'Australia/Sydney','utc':'UTC'}

def zone(name):
    return ZoneInfo(ALIASES.get(name.strip().lower(), name.strip()))

def get_current_time(timezone='Asia/Seoul'):
    return datetime.now(zone(timezone)).isoformat(timespec='seconds')

def connect():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('''CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, due REAL NOT NULL,
        timezone TEXT NOT NULL, kind TEXT NOT NULL, acknowledged INTEGER DEFAULT 0,
        UNIQUE(title, due, timezone, kind))''')
    return con

def save_entry(title, at, timezone='Asia/Seoul', kind='schedule'):
    if kind not in ('schedule', 'alarm') or not isinstance(title, str) or not title.strip():
        raise ValueError('종류 또는 제목이 올바르지 않습니다.')
    tz = zone(timezone)
    date = datetime.fromisoformat(at)
    if date.tzinfo is None:
        # 서머타임 경계에서 존재하지 않거나 두 번 나타나는 시각을 거부한다.
        a, b = date.replace(tzinfo=tz, fold=0), date.replace(tzinfo=tz, fold=1)
        if a.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != date:
            raise ValueError('해당 지역에 존재하지 않는 시각입니다.')
        if a.utcoffset() != b.utcoffset():
            raise ValueError('중복되는 시각입니다. UTC 오프셋을 포함해 주세요.')
        date = a
    stamp = date.timestamp()
    if stamp <= datetime.now(UTC).timestamp():
        raise ValueError('미래 날짜와 시간을 지정해 주세요.')
    with connect() as con:
        con.execute('INSERT OR IGNORE INTO entries(title,due,timezone,kind) VALUES(?,?,?,?)',
                    (title.strip(), stamp, tz.key, kind))
        row = con.execute('SELECT * FROM entries WHERE title=? AND due=? AND timezone=? AND kind=?',
                          (title.strip(), stamp, tz.key, kind)).fetchone()
    return format_entry(row)

def format_entry(row):
    d = dict(row)
    d['at'] = datetime.fromtimestamp(d.pop('due'), zone(d['timezone'])).isoformat(timespec='seconds')
    return d

def list_entries():
    with connect() as con:
        return [format_entry(r) for r in con.execute('SELECT * FROM entries ORDER BY due')]

def delete_entry(entry_id):
    with connect() as con:
        n = con.execute('DELETE FROM entries WHERE id=?', (int(entry_id),)).rowcount
    return {'deleted': bool(n), 'id': entry_id}

def due_alarms():
    with connect() as con:
        return [format_entry(r) for r in con.execute(
            "SELECT * FROM entries WHERE kind='alarm' AND acknowledged=0 AND due<=? ORDER BY due",
            (datetime.now(UTC).timestamp(),))]

def acknowledge(entry_id):
    with connect() as con:
        con.execute('UPDATE entries SET acknowledged=1 WHERE id=?', (entry_id,))

def fetch(url, **kwargs):
    query = urlencode(kwargs.get('params', {}))
    request = Request(url + '?' + query, headers=kwargs.get('headers', {}))
    with urlopen(request, timeout=20) as response:
        return json.load(response)

def search_location(city):
    # 도시명이 중복될 수 있으므로 후보를 모두 반환한다.
    return fetch('https://geocoding-api.open-meteo.com/v1/search',
                 params={'name': city, 'count': 5, 'language':'ko', 'format':'json'}).get('results', [])

def get_weather(latitude, longitude):
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('위도·경도 범위를 확인하세요.')
    result = fetch('https://api.open-meteo.com/v1/forecast', params={
        'latitude':latitude, 'longitude':longitude, 'timezone':'auto', 'forecast_days':3,
        'current':'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m',
        'daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code'})
    return {'source':'Open-Meteo (CC BY 4.0)', 'url':'https://open-meteo.com/',
            'note':'현재 값은 기상 모델 기반이며, 예보는 현지 날짜 기준 3일입니다.', 'data':result}

def search_news(query):
    cid, secret = os.getenv('NAVER_CLIENT_ID'), os.getenv('NAVER_CLIENT_SECRET')
    if not cid or not secret:
        return {'error':'뉴스 검색을 위해 .env에 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET을 입력하세요.'}
    result = fetch('https://naverapihub.apigw.ntruss.com/search/v1/news',
        headers={"X-NCP-APIGW-API-KEY-ID": cid,"X-NCP-APIGW-API-KEY": secret,},
        params={'query':query, 'display':10, 'sort':'date', "format":"json"})
    clean = lambda s: html.unescape(re.sub('<[^>]+>', '', s))
    return {'source':'네이버 뉴스 검색', 'note':'기사 전문이 아닌 검색 요약문입니다. pubDate는 제공 시각입니다.',
            'items':[{'title':clean(i['title']), 'summary':clean(i['description']),
                      'url':i.get('originallink') or i['link'], 'provided_at':i['pubDate']}
                     for i in result.get('items', [])]}

def spec(name, description, props, required):
    return {'type':'function','function':{'name':name,'description':description,
            'parameters':{'type':'object','properties':props,'required':required,'additionalProperties':False}}}

def string(description):
    return {'type':'string','description':description}

tools = [
    spec('get_current_time','현재 시간 조회', {'timezone':string('IANA 시간대. 예: Asia/Seoul')}, ['timezone']),
    spec('search_location','날씨 조회 전 도시 좌표 후보를 검색. 한국어 결과가 없으면 영문 도시명으로 다시 검색.', {'city':string('도시 이름')}, ['city']),
    spec('get_weather','검색한 좌표의 현재 날씨와 오늘부터 3일 예보',
         {'latitude':{'type':'number'},'longitude':{'type':'number'}}, ['latitude','longitude']),
    spec('search_news','키워드로 최신 뉴스 검색. 전문 열람 기능은 없음.', {'query':string('검색어')}, ['query']),
    spec('save_entry','사용자가 요청한 일정 또는 화면 알람 저장. 상대 시각은 현재 시각 기준 계산.',
         {'title':string('제목'), 'at':string('ISO 8601 날짜와 시간. 예: 2026-10-08T15:00:00+09:00'),
          'timezone':string('IANA 시간대'), 'kind':{'type':'string','enum':['schedule','alarm']}},
         ['title','at','timezone','kind']),
    spec('list_entries','저장된 모든 일정과 알람 조회', {}, []),
    spec('delete_entry','사용자가 삭제를 요청한 정확한 ID의 일정/알람 삭제. ID가 없으면 목록에서 확인.',
         {'entry_id':{'type':'integer'}}, ['entry_id']),
]
FUNCTIONS = {f.__name__:f for f in [get_current_time,search_location,get_weather,search_news,save_entry,list_entries,delete_entry]}

def dispatch(name, arguments):
    try:
        if name not in FUNCTIONS:
            return {'error':'지원하지 않는 도구입니다.'}
        if not isinstance(arguments, dict):
            return {'error':'인자는 JSON 객체여야 합니다.'}
        return FUNCTIONS[name](**arguments)
    except (URLError, TimeoutError):
        return {'error':'외부 서비스 연결 실패. 인터넷 연결, API 키 또는 서비스 상태를 확인하세요.'}
    except Exception as e:
        return {'error':str(e)}
