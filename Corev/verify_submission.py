"""Validate a relocatable submission without external API calls."""
from pathlib import Path
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

root = Path(__file__).resolve().parent
package = root / "submission/Corev-Windows"
python = package / "python/python.exe"
env = os.environ.copy()
for key in list(env):
    if key in {"OPENAI_API_KEY", "TYPESAFE_API_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
               "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "HF_TOKEN"}:
        env.pop(key)
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
checks = r'''
import sys, pathlib
print('Checking tkinter', flush=True)
import tkinter
print('Checking torch', flush=True)
import torch
print('Checking soundfile/transformers', flush=True)
import soundfile, transformers
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
import fastapi, uvicorn, typesafe_sdk, pandas, pymupdf, docx, openpyxl, reportlab
root = pathlib.Path(sys.executable).resolve().parent.parent
assert sys.flags.isolated
assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in sys.path)
print('Checking Tk window', flush=True)
window = tkinter.Tk(); window.withdraw(); window.destroy()
print('PASS: isolated Python; GUI; server, document and audio imports')
'''
result = subprocess.run([str(python), "-B", "-u", "-c", checks], env=env,
                        cwd=package.parent, timeout=150)
if result.returncode:
    raise SystemExit(result.returncode)
result = subprocess.run([str(python), "-B", str(package / "launcher.py"), "--smoke"],
                        env=env, cwd=package.parent, capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
print(result.stdout, flush=True)
if result.returncode:
    print(result.stderr)
    raise SystemExit(result.returncode)
forbidden = [p for p in package.rglob('*') if p.is_file() and
             (p.name == '.env' or p.suffix in {'.sqlite', '.sqlite3', '.db'} or
              p.name == 'pyvenv.cfg')]
assert not forbidden, [str(p.relative_to(package)) for p in forbidden]
print('PASS: no .env, chat databases or virtual-environment path config in submission')
