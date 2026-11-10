"""API가 반환한 사용량만 기록한다. 수신하지 못한 값은 None으로 유지한다."""
from contextvars import ContextVar
from uuid import uuid4

USAGE_SINK = ContextVar('usage_sink', default=None)


def record_usage(provider, model, stage, usage=None, note=''):
    usage = usage if isinstance(usage, dict) else {}
    def number(*keys):
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None
    incoming = number('input_tokens', 'prompt_tokens')
    outgoing = number('output_tokens', 'completion_tokens')
    total = number('total_tokens')
    if total is None and incoming is not None and outgoing is not None:
        total = incoming + outgoing
    item = dict(id=uuid4().hex, provider=provider, model=str(model), stage=stage,
                input_tokens=incoming, output_tokens=outgoing, total_tokens=total,
                note=note or ('API 반환값' if incoming is not None and outgoing is not None
                              else '확인 불가 · API 사용량 미수신'))
    sink = USAGE_SINK.get()
    if sink is not None:
        sink({'type': 'usage', 'data': item})
    return item


def jev_request(client, *, state, questions, stage, model):
    raw = None
    try:
        raw = client.system_one(state=state, questions=questions).model_dump(mode='json')
        return raw
    finally:
        record_usage('Jev', (raw or {}).get('model') or model, stage,
                     (raw or {}).get('usage'))


def summarize_usage(records):
    groups = {}
    seen = set()
    for item in records:
        if item['id'] in seen:
            continue
        seen.add(item['id'])
        key = (item['provider'], item['model'])
        group = groups.setdefault(key, {'서비스': key[0], '모델': key[1], '기록 수': 0,
            '입력': [], '출력': [], '합계': [], '누락': 0})
        group['기록 수'] += 1
        for label, field in [('입력','input_tokens'), ('출력','output_tokens'), ('합계','total_tokens')]:
            value = item.get(field)
            if value is not None:
                group[label].append(value)
        if any(item.get(f) is None for f in ('input_tokens','output_tokens','total_tokens')):
            group['누락'] += 1
    rows = []
    for group in groups.values():
        row = {k: group[k] for k in ('서비스','모델','기록 수')}
        for label in ('입력','출력','합계'):
            values = group[label]
            row[label] = (f"{sum(values):,}" + (' (확인분)' if len(values) < group['기록 수'] else '')) if values else '확인 불가'
        row['상태'] = f"{group['누락']}건 미확인 포함" if group['누락'] else '수집 완료'
        rows.append(row)
    return rows
