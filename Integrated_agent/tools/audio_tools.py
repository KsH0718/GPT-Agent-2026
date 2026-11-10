# integrated_agent/tools/audio_tools.py
"""음성 인식과 단계별 소요 시간 측정."""

from usage_tracking import record_usage

import csv
import json
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

from config import (
    OPENAI_API_KEY,
    WHISPER_MODEL_ID,
    FFMPEG_EXE,
)
from file_utils import (
    resolve_input_file,
    make_output_path,
    file_result,
)


LOCAL_MODEL_LOCK = threading.Lock()

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".flac",
    ".ogg", ".webm", ".mp4",
}


def log(message: str):
    """진행 상황을 터미널에 즉시 출력한다."""
    clock = datetime.now().strftime("%H:%M:%S")
    print(f"[음성 {clock}] {message}", flush=True)


def find_ffmpeg() -> str:
    configured = Path(FFMPEG_EXE)

    if configured.is_file():
        return str(configured.resolve())

    discovered = shutil.which(FFMPEG_EXE) or shutil.which("ffmpeg")

    if discovered:
        return discovered

    raise FileNotFoundError(
        "FFmpeg를 찾지 못했습니다. "
        "chap05/ffmpeg/bin/ffmpeg.exe를 확인해주세요."
    )


def run_ffmpeg(source: Path, destination: Path, output_args: list):
    """FFmpeg로 음성 형식을 변환한다."""
    try:
        subprocess.run(
            [
                find_ffmpeg(),
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(source),
                "-vn",
                *output_args,
                str(destination),
            ],
            capture_output=True,
            timeout=600,
            check=True,
        )

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "음성 변환 시간이 초과되었습니다."
        ) from error

    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "FFmpeg 변환 실패: 파일 손상 여부와 "
            "음성 트랙 유무를 확인해주세요."
        ) from error


@lru_cache(maxsize=1)
def load_local_transcriber():
    """서버 프로세스 안에서 모델을 한 번 불러오고 재사용한다."""
    import torch
    from transformers import (
        AutoModelForSpeechSeq2Seq,
        AutoProcessor,
        pipeline,
    )

    use_gpu = torch.cuda.is_available()
    dtype = torch.float16 if use_gpu else torch.float32
    device_name = "cuda" if use_gpu else "cpu"

    if use_gpu:
        log(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        log("CPU 사용: GPU보다 처리 시간이 길어질 수 있습니다.")

    log(f"모델 불러오기 시작: {WHISPER_MODEL_ID}")

    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        WHISPER_MODEL_ID,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        use_safetensors=True,
    ).to(device_name)

    processor = AutoProcessor.from_pretrained(
        WHISPER_MODEL_ID
    )

    transcriber = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=dtype,
        device=0 if use_gpu else -1,
        batch_size=1,
    )

    return transcriber, device_name


def transcribe_local(path: Path):
    record_usage("로컬", "Whisper", "로컬 음성 인식 시작",
                 note="로컬 실행 1회 · API 토큰 해당 없음")
    timings = {}

    started = time.perf_counter()

    import soundfile as sf
    import torch

    timings["라이브러리 준비"] = time.perf_counter() - started

    with tempfile.TemporaryDirectory(prefix="agent_audio_") as temp:
        wav_path = Path(temp) / "audio.wav"

        log("1. FFmpeg 음성 변환 시작")
        started = time.perf_counter()

        run_ffmpeg(
            path,
            wav_path,
            [
                "-ac", "1",
                "-ar", "16000",
                "-c:a", "pcm_s16le",
            ],
        )

        timings["FFmpeg 변환"] = time.perf_counter() - started
        log(f"1. 변환 완료: {timings['FFmpeg 변환']:.2f}초")

        started = time.perf_counter()

        samples, sample_rate = sf.read(
            str(wav_path),
            dtype="float32",
        )

        if samples.size == 0:
            raise ValueError("음성 데이터가 비어 있습니다.")

        duration = len(samples) / sample_rate
        timings["음성 파일 읽기"] = time.perf_counter() - started
        log(f"음성 길이: {duration:.1f}초")

        log("2. 로컬 모델 사용 대기")
        waiting_started = time.perf_counter()

        with LOCAL_MODEL_LOCK:
            timings["모델 사용 대기"] = (
                time.perf_counter() - waiting_started
            )

            cached = load_local_transcriber.cache_info().currsize > 0

            log(
                "3. 기존 모델 재사용"
                if cached
                else "3. 최초 모델 준비 시작"
            )

            started = time.perf_counter()
            transcriber, device_name = load_local_transcriber()

            # GPU 작업 완료를 기다려 단계별 시간을 구분한다.
            if device_name == "cuda":
                torch.cuda.synchronize()

            timings["모델 준비"] = time.perf_counter() - started
            log(f"3. 모델 준비 완료: {timings['모델 준비']:.2f}초")

            log("4. 실제 음성 인식 시작")
            started = time.perf_counter()

            with torch.inference_mode():
                result = transcriber(
                    {
                        "raw": samples,
                        "sampling_rate": sample_rate,
                    },
                    return_timestamps=True,
                    generate_kwargs={
                        "language": "korean",
                        "task": "transcribe",
                    },
                )

            if device_name == "cuda":
                torch.cuda.synchronize()

            timings["음성 인식"] = time.perf_counter() - started
            log(f"4. 음성 인식 완료: {timings['음성 인식']:.2f}초")

    rows = []

    for chunk in result.get("chunks", []):
        start, end = chunk.get("timestamp") or (None, None)

        rows.append({
            "start": start,
            "end": end,
            "text": str(chunk.get("text", "")).strip(),
        })

    timings["음성 길이"] = duration

    return (
        str(result.get("text", "")).strip(),
        rows,
        device_name,
        timings,
    )


def transcribe_openai(path: Path):
    from openai import OpenAI

    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 설정을 확인해주세요.")

    timings = {}

    with tempfile.TemporaryDirectory(prefix="agent_api_audio_") as temp:
        mp3_path = Path(temp) / "audio.mp3"

        log("1. API 전송용 음성 변환 시작")
        started = time.perf_counter()

        run_ffmpeg(
            path,
            mp3_path,
            [
                "-ac", "1",
                "-ar", "16000",
                "-codec:a", "libmp3lame",
                "-b:a", "48k",
            ],
        )

        timings["FFmpeg 변환"] = time.perf_counter() - started
        log(f"1. 변환 완료: {timings['FFmpeg 변환']:.2f}초")

        if mp3_path.stat().st_size > 24 * 1024 * 1024:
            raise ValueError(
                "변환 파일이 앱의 API 전송 제한 24MB를 넘었습니다. "
                "음성을 나누거나 로컬 방식을 사용해주세요."
            )

        log("2. OpenAI 음성 인식 요청 시작")
        started = time.perf_counter()

        with OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=180,
            max_retries=1,
        ) as client:
            with mp3_path.open("rb") as audio_file:
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    language="ko",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

        timings["API 요청 및 응답"] = time.perf_counter() - started
        log(
            "2. API 응답 완료: "
            f"{timings['API 요청 및 응답']:.2f}초"
        )

    data = response.model_dump()
    duration = data.get("duration")
    record_usage("OpenAI", "whisper-1", "음성 인식", data.get("usage"),
                 note=f"음성 길이 {duration}초 · 토큰 정보 미제공" if duration is not None
                 else "음성 인식 완료 · 토큰 정보 미제공")

    rows = [
        {
            "start": segment.get("start"),
            "end": segment.get("end"),
            "text": str(segment.get("text", "")).strip(),
        }
        for segment in (data.get("segments") or [])
    ]

    return (
        str(data.get("text", "")).strip(),
        rows,
        "OpenAI API",
        timings,
    )


@tool
def transcribe_audio(
    file_path: str,
    backend: Literal["local", "openai"] = "local",
) -> str:
    """한국어 음성을 인식하고 TXT와 시간 구간별 CSV를 저장한다.

    기본 local은 로컬 Whisper를 사용한다.
    openai는 사용자가 API 방식을 요청하거나 선택했을 때 사용한다.
    실패 시 임의로 다른 방식으로 전환하지 않는다.
    CSV는 start, end, text 열과 | 구분자를 사용한다.
    화자 구분은 지원하지 않는다.
    긴 결과는 반환된 TXT 경로를 read_document로 읽는다.
    """
    created_paths = []
    total_started = time.perf_counter()

    try:
        path = resolve_input_file(file_path)

        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError("지원하지 않는 음성 파일 형식입니다.")

        log(f"작업 시작 / 방식: {backend}")

        if backend == "local":
            text, rows, device, timings = transcribe_local(path)

        elif backend == "openai":
            text, rows, device, timings = transcribe_openai(path)

        else:
            raise ValueError("local 또는 openai를 선택해주세요.")

        if not text:
            raise ValueError("인식된 텍스트가 없습니다.")

        log("5. TXT·CSV 저장 시작")
        save_started = time.perf_counter()

        txt_path = make_output_path(
            f"{path.stem}_transcript", "txt"
        )
        created_paths.append(txt_path)
        txt_path.write_text(text, encoding="utf-8")

        files = [file_result(txt_path)]

        if rows:
            csv_path = make_output_path(
                f"{path.stem}_segments", "csv"
            )
            created_paths.append(csv_path)

            with csv_path.open(
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["start", "end", "text"],
                    delimiter="|",
                )
                writer.writeheader()
                writer.writerows(rows)

            files.append(file_result(csv_path))

        timings["파일 저장"] = time.perf_counter() - save_started
        timings["음성 도구 전체"] = time.perf_counter() - total_started

        log(f"5. 저장 완료: {timings['파일 저장']:.2f}초")
        log(
            f"음성 도구 완료: 총 {timings['음성 도구 전체']:.2f}초 "
            f"/ {len(text)}자 / 시간 구간 {len(rows)}개"
        )
        log("이후 AI 요약·Word 생성 시간은 위 측정에 포함되지 않습니다.")

        preview_limit = 16000

        return json.dumps({
            "성공": True,
            "인식 방식": backend,
            "실행 장치": device,
            "소요 시간(초)": {
                key: round(value, 2)
                for key, value in timings.items()
            },
            "전체 글자 수": len(text),
            "텍스트": text[:preview_limit],
            "텍스트 일부만 표시": len(text) > preview_limit,
            "시간 구간 수": len(rows),
            "생성 파일": files,
            "안내": (
                "화자 구분은 수행하지 않았습니다. "
                "시간은 초 단위이며 알 수 없는 시각은 CSV에서 빈칸입니다. "
                "텍스트가 일부만 표시되면 TXT 파일을 이어서 읽어주세요."
            ),
            "CSV 안내": (
                "시간 구간별 CSV를 저장했습니다."
                if rows
                else "시간 구간이 반환되지 않아 TXT만 저장했습니다."
            ),
        }, ensure_ascii=False)

    except Exception as error:
        log(
            f"실패 / {type(error).__name__}: {error} "
            f"/ 경과 {time.perf_counter() - total_started:.2f}초"
        )

        for path in created_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

        return json.dumps({
            "성공": False,
            "오류": str(error),
            "오류 종류": type(error).__name__,
        }, ensure_ascii=False)


AUDIO_TOOLS = [transcribe_audio]


if __name__ == "__main__":
    print("음성 인식 도구 준비 완료!")

    try:
        print("FFmpeg:", find_ffmpeg())
    except FileNotFoundError as error:
        print(error)

    print("실제 음성 처리 시 단계별 시간이 터미널에 표시됩니다.")