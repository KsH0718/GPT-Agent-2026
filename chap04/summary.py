import os
from pathlib import Path
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

# 최상위 폴더의 .env 파일 위치를 자동으로 찾아 로드
load_dotenv(find_dotenv())

# 현재 summary.py 파일이 있는 폴더 (chap04)
BASE_DIR = Path(__file__).resolve().parent


def summarize_txt(file_path: str):
    api_key = os.getenv('OPENAI_API_KEY')

    if not api_key:
        raise ValueError(
            ".env 파일에서 OPENAI_API_KEY를 찾을 수 없습니다. 경로를 확인해주세요."
        )

    client = OpenAI(api_key=api_key)

    with open(file_path, 'r', encoding='utf-8') as f:
        txt = f.read()

    system_prompt = f'''
    너는 다음 글을 요약하는 봇이다. 아래 글을 읽고, 저자의 문제 인식과 주장을 파악하여 주요 내용을 요약하라.

    작성해야 하는 포맷은 다음과 같다.

    # [원문 텍스트의 정확한 전체 제목]

    ## 저자의 문제 인식 및 주장 (15문장 이내)

    ## 저자 소개

    [주의 사항]
    - 최상단 `#` 제목은 생략이나 변형 없이 원문 텍스트의 전체 제목을 토시 하나 틀리지 않고 그대로 작성하라.

    ================= 아래 텍스트 =================

    {txt}

    '''

    print(system_prompt)
    print('============================================')

    response = client.chat.completions.create(
        model='gpt-4o',
        temperature=0.1,
        messages=[{"role": "system", "content": system_prompt}],
    )

    return response.choices[0].message.content


if __name__ == '__main__':
    # './chap04/output/...' 대신 BASE_DIR을 활용한 absolute path 구성
    input_file = (
        BASE_DIR
        / 'output'
        / '과정기반 작물모형을 이용한 웹 기반 밀 재배관리 의사결정 지원시스템 설계 및 구축_with_preprocessing.txt'
    )
    summary = summarize_txt(str(input_file))
    print(summary)

    output_file = BASE_DIR / 'output' / 'crop_model_summary.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(summary)
