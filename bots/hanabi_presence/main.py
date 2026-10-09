"""小花火 (Hanabiの小天地 bot) — 只負責「上線狀態」的綠點。

小花火的指令（/quiz /grammar /dictionary /language /help）由 Cloudflare Worker
hanabi-discord 透過 HTTP interactions 回答（程式在網站 repo 的 worker/discord/），
Worker 沒辦法一直掛著 Discord 的 gateway 連線，所以成員列表會顯示離線。這支程式
只做一件事：用小花火的 token 連上 gateway、顯示「正在玩 單字庫」。

注意：
- 不要在這裡建立或同步任何指令（不用 app_commands / tree.sync），否則會蓋掉
  Worker 註冊的指令。指令的事件也不會送到這裡：後台設了 Interactions Endpoint URL，
  Discord 會把它們送到 Worker。
- 不需要任何 intents（不讀訊息、不看成員）。
- 沒設定 DISCORD_TOKEN（Render 上的 HANABI_DISCORD_TOKEN）時就安靜等待，
  不要結束：supervisor 會在程式結束 5 秒後重啟，會變成一直重啟。
"""
import os
import time

import discord

TOKEN = os.getenv("DISCORD_TOKEN")


class Presence(discord.Client):
    async def on_ready(self):
        print(f"[hanabi_presence] 已上線：{self.user}（{len(self.guilds)} 個伺服器）", flush=True)


def main():
    if not TOKEN:
        print("[hanabi_presence] 沒有設定 HANABI_DISCORD_TOKEN，先不上線", flush=True)
        while True:
            time.sleep(3600)
    client = Presence(
        intents=discord.Intents.none(),
        status=discord.Status.online,
        activity=discord.Game(name="單字庫"),
    )
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
