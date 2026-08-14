import os
import sys
import time
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 每支 bot 的設定：
#   dir     - bot 程式碼所在資料夾（用來當子程序的工作目錄，讓相對 import 正常運作）
#   cmd     - 啟動指令
#   env_map - {子程序內程式碼原本讀取的變數名稱: Render 上要另外設定的專屬變數名稱}
#             這樣三隻 bot 就算原本都叫 DISCORD_TOKEN，也不會互撞
BOTS = [
    {
        "name": "pp_checker",
        "dir": os.path.join(BASE_DIR, "bots", "pp_checker"),
        "cmd": [sys.executable, "main.py"],
        "env_map": {
            "DISCORD_TOKEN": "PP_DISCORD_TOKEN",
            "OSU_CLIENT_ID": "OSU_CLIENT_ID",
            "OSU_CLIENT_SECRET": "OSU_CLIENT_SECRET",
        },
    },
    {
        "name": "miku39",
        "dir": os.path.join(BASE_DIR, "bots", "miku39"),
        "cmd": [sys.executable, "main.py"],
        "env_map": {
            "TOKEN": "MIKU_TOKEN",
            "OSU_API_KEY": "MIKU_OSU_API_KEY",
        },
    },
    {
        "name": "osu_bot",
        "dir": os.path.join(BASE_DIR, "bots", "osu_bot"),
        "cmd": [sys.executable, "bot.py"],
        "env_map": {
            "DISCORD_TOKEN": "OSU_BOT_DISCORD_TOKEN",
            "FIREBASE_CREDENTIALS": "FIREBASE_CREDENTIALS",
        },
    },
]


def build_env(env_map):
    env = os.environ.copy()
    for target_name, source_name in env_map.items():
        value = os.environ.get(source_name)
        if value is not None:
            env[target_name] = value
    env["SUPERVISED"] = "1"
    return env


def run_bot(bot):
    while True:
        print(f"[supervisor] 啟動 {bot['name']} ...", flush=True)
        proc = subprocess.Popen(
            bot["cmd"],
            cwd=bot["dir"],
            env=build_env(bot["env_map"]),
        )
        proc.wait()
        print(
            f"[supervisor] {bot['name']} 已結束（exit code {proc.returncode}），5 秒後重啟...",
            flush=True,
        )
        time.sleep(5)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"3 bots supervised and running")

    def log_message(self, format, *args):
        pass  # 不印出每次健康檢查的 request log，避免洗版


def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=run_health_server, daemon=True).start()

    threads = []
    for bot in BOTS:
        th = threading.Thread(target=run_bot, args=(bot,), daemon=True)
        th.start()
        threads.append(th)

    for th in threads:
        th.join()
