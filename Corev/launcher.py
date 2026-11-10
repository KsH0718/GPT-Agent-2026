"""Local Corev launcher. All build artifacts and launcher logs stay here."""
from pathlib import Path
import functools
import http.server
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
PYTHON = PROJECT / "venv/Scripts/python.exe"
WEB = ROOT / "runtime/flutter/build/web"
LOGS = ROOT / "logs"
HIDDEN = subprocess.CREATE_NO_WINDOW
EVENTS = queue.Queue()


def status(text):
    EVENTS.put(text)
    if "--smoke" in sys.argv:
        print(text, flush=True)


def chrome_path():
    for base in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        path = Path(os.environ.get(base, "")) / "Google/Chrome/Application/chrome.exe"
        if path.is_file():
            return path
    raise RuntimeError("Google Chrome을 찾을 수 없습니다. Chrome 설치 경로를 확인하세요.")


def build():
    flutter = shutil.which("flutter")
    if not flutter:
        candidate = Path.home() / "src/flutter/bin/flutter.bat"
        flutter = str(candidate) if candidate.is_file() else None
    if not flutter:
        raise RuntimeError("Flutter SDK를 찾을 수 없습니다. Flutter를 PATH에 등록하세요.")
    status("최초 화면 준비 중입니다. 빌드에 몇 분 걸릴 수 있습니다.")
    target = ROOT / "runtime/flutter"
    target.mkdir(parents=True, exist_ok=True)
    # Copy only web build inputs; never run Flutter in the original checkout.
    for name in ("lib", "assets", "web"):
        source = PROJECT / "flutter_app" / name
        if source.exists():
            shutil.copytree(source, target / name, dirs_exist_ok=True)
    for name in ("pubspec.yaml", "pubspec.lock", "analysis_options.yaml"):
        source = PROJECT / "flutter_app" / name
        if source.exists():
            shutil.copy2(source, target / name)
    with (LOGS / "build.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [flutter, "build", "web", "--release"],
            cwd=target, stdout=log, stderr=subprocess.STDOUT,
            creationflags=HIDDEN,
        )
    if result.returncode or not (WEB / "index.html").is_file():
        raise RuntimeError("화면 빌드 실패: Corev/logs/build.log를 확인하세요.")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


class Runtime:
    def __init__(self):
        self.backend = None
        self.web = None
        self.log = None
        self.guard = None

    def start(self, browser=True):
        LOGS.mkdir(exist_ok=True)
        self.guard = socket.socket()
        try:
            self.guard.bind(("127.0.0.1", 18765))
        except OSError:
            raise RuntimeError("Corev가 이미 실행 중이거나 18765 포트가 사용 중입니다. 실행 관리자를 확인하세요.")
        self.guard.listen(1)
        if not PYTHON.is_file():
            raise RuntimeError("상위 폴더의 venv/Scripts/python.exe가 없습니다.")
        chrome = chrome_path() if browser else None
        # Never kill or take over an unrelated service.
        with socket.socket() as check:
            try:
                check.bind(("127.0.0.1", 8000))
            except OSError:
                raise RuntimeError("8000 포트가 사용 중입니다. 기존 서버를 종료한 뒤 다시 실행하세요.")
        if "--rebuild" in sys.argv or not (WEB / "index.html").is_file():
            build()
        status("AI 서버 시작 중...")
        self.log = (LOGS / "server.log").open("w", encoding="utf-8")
        self.backend = subprocess.Popen(
            [str(PYTHON), "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", "8000"],
            cwd=PROJECT / "Integrated_agent",
            stdout=self.log, stderr=subprocess.STDOUT, creationflags=HIDDEN,
        )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.backend.poll() is not None:
                raise RuntimeError("AI 서버 시작 실패: Corev/logs/server.log를 확인하세요.")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1) as reply:
                    if json.load(reply).get("status") == "AI Agent FastAPI Server is running!":
                        break
            except (OSError, ValueError):
                time.sleep(.5)
        else:
            raise RuntimeError("AI 서버 준비 시간이 초과되었습니다. server.log를 확인하세요.")
        handler = functools.partial(QuietHandler, directory=str(WEB))
        self.web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.web.daemon_threads = True
        threading.Thread(target=self.web.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.web.server_port}/"
        if browser:
            subprocess.Popen(
                [str(chrome), f"--app={self.url}", "--new-window"],
                creationflags=HIDDEN,
            )
        status("실행 중 — 앱 창을 닫은 뒤 이 제어창의 ‘Corev 종료’를 눌러 주세요.")

    def close(self):
        if self.web:
            self.web.shutdown()
            self.web.server_close()
        if self.backend and self.backend.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(self.backend.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=HIDDEN,
            )
        if self.log:
            self.log.close()
        if self.guard:
            self.guard.close()


def main():
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    runtime = Runtime()
    if "--smoke" in sys.argv:
        try:
            runtime.start(browser=False)
            with urllib.request.urlopen(runtime.url) as response:
                assert response.status == 200
                assert b"flutter_bootstrap.js" in response.read()
            with urllib.request.urlopen(runtime.url + "main.dart.js") as response:
                assert response.status == 200
                assert len(response.read()) > 0
            with urllib.request.urlopen("http://127.0.0.1:8000/capabilities") as response:
                assert len(json.load(response)["tools"]) > 0
            print("PASS: web assets + backend capabilities; shutting down", flush=True)
        finally:
            runtime.close()
        return

    import tkinter as tk
    from tkinter import messagebox
    window = tk.Tk()
    window.title("Corev 실행 관리자")
    window.geometry("560x180")
    window.resizable(False, False)
    label = tk.Label(window, text="Corev 준비 중...", wraplength=520, pady=22)
    label.pack()
    ready = threading.Event()
    failed = []

    def worker():
        try:
            runtime.start()
        except Exception as error:
            runtime.close()
            failed.append(str(error))
        finally:
            ready.set()

    def close():
        if not ready.is_set():
            messagebox.showinfo("Corev", "준비가 끝난 뒤 종료해 주세요.")
            return
        runtime.close()
        window.destroy()

    button = tk.Button(window, text="Corev 종료 (서버 함께 종료)", command=close)
    button.pack(pady=10)
    window.protocol("WM_DELETE_WINDOW", close)

    def update():
        while not EVENTS.empty():
            label.config(text=EVENTS.get_nowait())
        if failed:
            messagebox.showerror("Corev 실행 실패", failed.pop())
            window.destroy()
            return
        window.after(200, update)

    threading.Thread(target=worker, daemon=True).start()
    window.after(200, update)
    window.mainloop()


if __name__ == "__main__":
    main()
