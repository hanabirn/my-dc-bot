# main.py 的最上方導入區
import os
import asyncio
from discord.ext import commands
import discord
from dotenv import load_dotenv

# === 新增：導入 Flask 與 Threading ===
from flask import Flask
import threading

# 保持您原本的導入
from mikuCommands import register_commands
from osu_interactions import handle_play_interactions

load_dotenv()
TOKEN = os.getenv("TOKEN")

# 只監聽這個 Discord user ID 發的訊息（那支真正在貼戰績的 bot），避免把任何 bot
# 的訊息都當成戰績分析——之前用「message.author.bot」判斷太寬，連 osu_bot 自己
# 的 !help 選單（文字裡剛好有 "recent"、"pp"）都會被誤判成戰績訊息。
_target_bot_id_raw = os.getenv("TARGET_BOT_ID")
TARGET_BOT_ID = int(_target_bot_id_raw) if _target_bot_id_raw else None
if TARGET_BOT_ID is None:
    print("⚠️ 未設定 TARGET_BOT_ID，osu! 戰績訊息偵測功能已停用")

# === 新增：建立一個簡單的 Flask 伺服器，讓 Render 能夠進行健康檢查 ===
app = Flask(__name__)

@app.route('/')
def home():
    return "Miku Bot is alive and running!"

def run_web_server():
    # Render 會自動配置 PORT 環境變數，如果本機測試沒有就用 10000
    port = int(os.environ.get("PORT", 10000))
    # host 必須設定為 0.0.0.0 才能讓外部訪問
    app.run(host="0.0.0.0", port=port)
# ==========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="bot ", intents=intents, help_command=None)

# Slash 指令同步到這個伺服器（幾乎立即生效，不用等 Discord 全域同步最長 1 小時的傳播時間）
GUILD = discord.Object(id=1505477519753609226)

register_commands(bot)

async def handle_osu_message(message: discord.Message):
    await asyncio.sleep(1.5)
    try:
        content_text = message.content or ""
        embed_title = message.embeds[0].title or "" if message.embeds else ""
        embed_desc = message.embeds[0].description or "" if message.embeds else ""

        embed_fields_text = ""
        if message.embeds and message.embeds[0].fields:
            embed_fields_text = " ".join([f"{f.name} {f.value}" for f in message.embeds[0].fields])

        all_text = f"{content_text} {embed_title} {embed_desc} {embed_fields_text}"
        # 已經在 on_message 篩過發訊息的是不是目標 bot 了，這裡不用再靠關鍵字
        # 猜測是不是戰績訊息——直接交給 handle_play_interactions 找命中分佈括號，
        # 找不到就直接沒反應，不會誤判。
        await handle_play_interactions(message, all_text)
    except Exception as e:
        print(f"分析 osu! 訊息時發生錯誤: {e}")

@bot.event
async def setup_hook():
    bot.tree.copy_global_to(guild=GUILD)
    synced = await bot.tree.sync(guild=GUILD)
    print(f"✅ 已同步 {len(synced)} 個 Slash 指令到伺服器")

@bot.event
async def on_ready():
    print(f"💚 世界第一公主殿下 MIKU39 已登入為: {bot.user}")

@bot.event
async def on_message(message: discord.Message):
    if TARGET_BOT_ID is not None and message.author.id == TARGET_BOT_ID:
        await handle_osu_message(message)
        return

    await bot.process_commands(message)

# === 修改：原本最後一行的 bot.run(TOKEN) 改為以下結構 ===
if __name__ == "__main__":
    # 1. 在背景啟動 Flask 網頁伺服器
    # 由 supervisor.py 統一啟動時（SUPERVISED=1），健康檢查改由 supervisor 負責，
    # 避免三隻 bot 各自搶同一個 port
    if not os.getenv("SUPERVISED"):
        t = threading.Thread(target=run_web_server)
        t.daemon = True # 設定為守護執行緒，主程式結束時會自動關閉
        t.start()

    # 2. 啟動您的 Discord 機器人
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("錯誤：找不到 TOKEN 環境變數，請檢查您的 .env 或 Render 參數設定。")