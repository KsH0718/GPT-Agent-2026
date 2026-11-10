"""User-authorized professor-only credential inclusion. Never prints values."""
from pathlib import Path
import json
import os
import sys

root = Path(__file__).resolve().parent
package = root / 'submission/Corev-Windows'
sys.path.insert(0, str(root.parent / 'Integrated_agent'))
import config

keys = ('OPENAI_API_KEY', 'TYPESAFE_API_KEY', 'NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET',
        'OPENAI_MODEL', 'JEV_MODEL')
values = {key: getattr(config, key, '') for key in keys}
assert values['OPENAI_API_KEY'], 'No existing OpenAI API key was found'
destination = package / 'private-api.env'
destination.write_text(''.join(f'{key}={json.dumps(value, ensure_ascii=False)}\n'
                               for key, value in values.items()), encoding='utf-8')
launcher = package / 'launcher.py'
text = launcher.read_text(encoding='utf-8')
anchor = '    if "--smoke" not in sys.argv:\n'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '''        DATA.mkdir(parents=True, exist_ok=True)
        if not (DATA / ".env").exists() and (ROOT / "private-api.env").is_file():
            shutil.copy2(ROOT / "private-api.env", DATA / ".env")
''', 1)
launcher.write_text(text, encoding='utf-8')
readme = package / 'START_HERE.txt'
text = readme.read_text(encoding='utf-8')
text = text.replace('Corev — 교수님 제출용 Windows 실행본',
                    'Corev — 교수님 전달 전용 비공개 Windows 실행본 (API 키 포함)')
text = text.replace('3. 첫 실행의 API 설정에서 본인의 키를 입력하고 저장합니다.\n   빈칸으로 저장해도 UI와 기능 목록은 확인할 수 있지만 AI 답변은 사용할 수 없습니다.',
                    '3. 첫 실행 시 제출자의 API 설정을 자동으로 적용합니다.\n   기존 Corev 설정이 있으면 보존합니다. 변경 시 API-settings.cmd를 사용하세요.')
text = text.replace('- 개발자의 API 키와 대화 기록은 포함하지 않습니다.',
                    '- 제출자의 명시적 요청에 따라 API 키를 포함합니다. 대화 기록은 포함하지 않습니다.\n- 교수님에게만 비공개로 전달하세요. 공개 게시·재배포하지 마세요.\n- private-api.env와 사용자 데이터 폴더의 키는 평문이며 추출 가능합니다.\n- 평가 후 제출자는 키를 교체/폐기하여 추가 사용을 차단할 수 있습니다.')
readme.write_text(text, encoding='utf-8')
print('Private professor configuration prepared; credential values were not logged.')
