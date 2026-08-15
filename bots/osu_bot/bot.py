import os
import json
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
import discord
from discord.ext import commands
import firebase_admin
from firebase_admin import credentials

# ========================================================
# ⚙️ 測試專用設定區（此處保持你原有的變數邏輯）
# ========================================================
LOCAL_DISCORD_TOKEN = ""  # 👈 推進 GitHub 前請保持留空
LOCAL_API_KEY = ""        # 👈 推進 GitHub 前請保持留空

FIREBASE_URL = "https://osu-discord-bot-56c1d-default-rtdb.firebaseio.com/"

# ========================================================
# 1. 防止 Render 斷線的防斷線伺服器
# ========================================================
def run_dummy_server():
    try:
        server = HTTPServer(('0.0.0.0', 10000), SimpleHTTPRequestHandler)
        server.serve_forever()
    except Exception:
        pass

# 由 supervisor.py 統一啟動時（SUPERVISED=1），健康檢查改由 supervisor 負責，
# 避免三隻 bot 各自搶同一個 port 10000
if not os.getenv("SUPERVISED"):
    threading.Thread(target=run_dummy_server, daemon=True).start()

# ========================================================
# 2. 智慧安全防護
# ========================================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", LOCAL_DISCORD_TOKEN)

# ========================================================
# 3. Firebase 智慧雙連線
# ========================================================
if not firebase_admin._apps:
    env_creds = os.getenv("FIREBASE_CREDENTIALS")
    if env_creds:
        cred_dict = json.loads(env_creds)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("firebase_key.json")
        
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_URL
    })

# ========================================================
# 4. 機器人核心啟動設定
# ========================================================
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
async def setup_hook():
    try:
        await bot.load_extension("cogs.osu_commands")
        print("✅ 成功載入 cogs.osu_commands 功能模組！")
    except Exception as e:
        print(f"❌ 載入 osu_commands 失敗: {e}")

@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name="!osu"))
    print(f"\n👾 {bot.user.name} 永不逾時版（已完全模組化拆分）已成功上線！")

bot.run(DISCORD_TOKEN)