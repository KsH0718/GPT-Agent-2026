"""Assemble an isolated Windows x64 submission using installed distributions.

Explicit source allowlists prevent copying .env, chats, uploads and reports.
Run with the project's venv Python. Refuses to overwrite existing output.
"""
from pathlib import Path
import importlib.metadata as metadata
import json
import os
import shutil
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUT = ROOT / "submission" / "Corev-Windows"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one template anchor: {old[:60]}")
    return text.replace(old, new, 1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if OUT.exists():
        raise RuntimeError("Existing submission is preserved. Select a new output version.")
    OUT.mkdir(parents=True)
    base = Path(sys.base_prefix)
    runtime = OUT / "python"
    runtime.mkdir()
    # Installed CPython is relocatable when no pyvenv.cfg is copied.
    for file in base.iterdir():
        if file.is_file() and (file.suffix.lower() in {".exe", ".dll"} or file.name.startswith("LICENSE")):
            shutil.copy2(file, runtime / file.name)
    for name in ("DLLs", "Lib", "tcl"):
        shutil.copytree(base / name, runtime / name,
                        ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc", "test", "tests"))
    site = runtime / "Lib/site-packages"
    site.mkdir(exist_ok=True)
    (runtime / "python312._pth").write_text(
        ".\nLib\nDLLs\nLib/site-packages\n..\n../Integrated_agent\nimport site\n",
        encoding="ascii")
    pending = [(name, frozenset()) for name in (
        "fastapi", "uvicorn", "python-multipart", "langchain-openai",
        "python-dotenv", "pandas", "pytz", "yfinance", "python-docx",
        "openpyxl", "pymupdf", "reportlab", "Pillow", "typesafe-sdk",
        "torch", "transformers", "accelerate", "tzdata", "soundfile",
    )]
    visited = set()
    distributions = {}
    while pending:
        name, extras = pending.pop()
        name = canonicalize_name(name)
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        dist = metadata.distribution(name)
        distributions[name] = dist
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            if requirement.marker and not any(
                requirement.marker.evaluate({"extra": extra}) for extra in ("", *extras)
            ):
                continue
            pending.append((requirement.name, frozenset(requirement.extras)))
    original_site = (Path(sys.prefix) / "Lib/site-packages").resolve()
    for name, dist in sorted(distributions.items()):
        print(f"Bundling {name} {dist.version}", flush=True)
        for relative in dist.files or []:
            source = Path(dist.locate_file(relative)).resolve()
            if not source.is_relative_to(original_site) or not source.is_file():
                continue
            if "__pycache__" in source.parts or source.suffix in {".pyc", ".pth"}:
                continue
            if source.name == ".env" or source.suffix in {".sqlite", ".sqlite3", ".db"}:
                continue
            dest = site / source.relative_to(original_site)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    (OUT / "DEPENDENCIES.txt").write_text(
        "\n".join(f"{name}=={dist.version}" for name, dist in sorted(distributions.items())),
        encoding="utf-8")
    backend = OUT / "Integrated_agent"
    backend.mkdir()
    for name in ("agent.py", "server.py", "config.py", "chat_store.py", "file_utils.py", "usage_tracking.py"):
        shutil.copy2(PROJECT / "Integrated_agent" / name, backend / name)
    (backend / "tools").mkdir()
    for source in (PROJECT / "Integrated_agent/tools").glob("*.py"):
        shutil.copy2(source, backend / "tools" / source.name)
    config = (backend / "config.py").read_text(encoding="utf-8")
    config = replace_once(config, "BASE_DIR = Path(__file__).resolve().parent",
                          'BASE_DIR = Path(os.environ["COREV_DATA"])')
    begin = config.index("ENV_CANDIDATES = [")
    end = config.index("\n]", begin) + 2
    config = config[:begin] + 'ENV_CANDIDATES = [BASE_DIR / ".env"]' + config[end:]
    (backend / "config.py").write_text(config, encoding="utf-8")
    store = (backend / "chat_store.py").read_text(encoding="utf-8")
    store = replace_once(store, 'DATA_DIR = Path(__file__).resolve().parent / "data"',
                         'import os\nDATA_DIR = Path(os.environ["COREV_DATA"]) / "data"')
    (backend / "chat_store.py").write_text(store, encoding="utf-8")
    shutil.copytree(ROOT / "runtime/flutter/build/web", OUT / "web")
    flutter_source = OUT / "source/flutter_app"
    flutter_source.mkdir(parents=True)
    for name in ("lib", "assets", "web"):
        shutil.copytree(PROJECT / "flutter_app" / name, flutter_source / name)
    for name in ("pubspec.yaml", "pubspec.lock"):
        shutil.copy2(PROJECT / "flutter_app" / name, flutter_source / name)
    shutil.copytree(PROJECT / "chap05/ffmpeg", OUT / "ffmpeg")
    shutil.copy2(ROOT / "submission_settings.py", OUT / "submission_settings.py")
    shutil.copy2(ROOT / "Corev.ico", OUT / "Corev.ico")
    launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
    launcher = replace_once(launcher, "PROJECT = ROOT.parent", "PROJECT = ROOT")
    launcher = replace_once(launcher, 'PYTHON = PROJECT / "venv/Scripts/python.exe"',
                             'PYTHON = ROOT / "python/python.exe"')
    launcher = replace_once(launcher, 'WEB = ROOT / "runtime/flutter/build/web"',
                             'WEB = ROOT / "web"')
    launcher = replace_once(launcher, 'LOGS = ROOT / "logs"', '''
DATA = (ROOT.parent / "validation-data" if "--smoke" in sys.argv else
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CorevSubmission")
os.environ["COREV_DATA"] = str(DATA)
os.environ["FFMPEG_EXE"] = str(ROOT / "ffmpeg/bin/ffmpeg.exe")
os.environ["HF_HOME"] = str(DATA / "models")
LOGS = DATA / "logs"
'''.strip())
    launcher = replace_once(launcher, "LOGS.mkdir(exist_ok=True)", "LOGS.mkdir(parents=True, exist_ok=True)")
    launcher = replace_once(launcher, '''        if "--rebuild" in sys.argv or not (WEB / "index.html").is_file():
            build()''', '''        if not (WEB / "index.html").is_file():
            raise RuntimeError("web 폴더가 없습니다. ZIP 전체를 압축 해제하세요.")''')
    # Accept Edge on PCs without Chrome, without requiring an extra installation.
    launcher = replace_once(launcher,
        '    raise RuntimeError("Google Chrome을 찾을 수 없습니다. Chrome 설치 경로를 확인하세요.")',
        '''    for base in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        path = Path(os.environ.get(base, "")) / "Microsoft/Edge/Application/msedge.exe"
        if path.is_file():
            return path
    raise RuntimeError("Chrome 또는 Microsoft Edge가 필요합니다.")''')
    launcher = replace_once(launcher, "    runtime = Runtime()", '''    if "--smoke" not in sys.argv:
        if "--settings" in sys.argv or not (DATA / ".env").exists():
            from submission_settings import configure
            configure()
            if "--settings" in sys.argv:
                return
    runtime = Runtime()''')
    (OUT / "launcher.py").write_text(launcher, encoding="utf-8")
    for filename, flag in (("Corev.cmd", ""), ("API-settings.cmd", " --settings")):
        (OUT / filename).write_text(
            '@echo off\nsetlocal\ncd /d "%~dp0"\n'
            f'start "" "%~dp0python\\pythonw.exe" "%~dp0launcher.py"{flag}\n',
            encoding="ascii")
    shutil.copy2(ROOT / "SUBMISSION_README.txt", OUT / "START_HERE.txt")
    print(f"READY: {OUT}", flush=True)


if __name__ == "__main__":
    main()
