"""First-run settings for the submission package; never reads developer keys."""
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def configure():
    data = Path(os.environ["COREV_DATA"])
    data.mkdir(parents=True, exist_ok=True)
    path = data / ".env"
    from dotenv import dotenv_values
    previous = dotenv_values(path) if path.exists() else {}
    window = tk.Tk()
    window.title("Corev API 설정")
    tk.Label(window, text="본인의 API 키를 입력하세요. 빈칸으로도 화면을 확인할 수 있습니다.\n"
             "키는 이 PC의 사용자 데이터 폴더에 평문으로 저장됩니다.\n"
             "실제 API 사용료는 입력한 키의 계정에 청구됩니다.",
             padx=20, pady=15).grid(row=0, column=0, columnspan=2)
    entries = {}
    fields = [
        ("OPENAI_API_KEY", "OpenAI API 키 (대화)"),
        ("TYPESAFE_API_KEY", "Jev API 키 (선택)"),
        ("NAVER_CLIENT_ID", "Naver Client ID (선택)"),
        ("NAVER_CLIENT_SECRET", "Naver Client Secret (선택)"),
    ]
    for row, (key, title) in enumerate(fields, 1):
        tk.Label(window, text=title).grid(row=row, column=0, sticky="w", padx=15)
        entry = tk.Entry(window, show="*", width=45)
        entry.insert(0, previous.get(key) or "")
        entry.grid(row=row, column=1, padx=15, pady=6)
        entries[key] = entry

    def save():
        values = {key: entry.get().strip() for key, entry in entries.items()}
        if any(any(c in value for c in "\r\n'\\") for value in values.values()):
            messagebox.showerror("입력 확인", "키에 줄바꿈, 작은따옴표, 역슬래시를 넣을 수 없습니다.")
            return
        text = "".join(f"{key}='{value}'\n" for key, value in values.items())
        temporary = path.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
        window.destroy()

    tk.Button(window, text="설정 저장", command=save).grid(
        row=5, column=0, columnspan=2, pady=18)
    window.mainloop()
