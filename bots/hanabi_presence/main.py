"""小花火 (Hanabiの小天地 bot) — 上線狀態的綠點，以及「回覆小花火」的聊天。

小花火的指令（/quiz /grammar /dictionary /ask /language /help）由 Cloudflare Worker
hanabi-discord 透過 HTTP interactions 回答（程式在網站 repo 的 worker/discord/），
Worker 沒辦法一直掛著 Discord 的 gateway 連線，所以這支程式負責兩件事：

1. 用小花火的 token 連上 gateway、顯示「正在玩 單字庫」（成員列表的綠點）。
2. 有人「回覆小花火的訊息」或「@小花火」時（2026-10-15 加入），把這串回覆
   （往上最多 HISTORY 則）送到 Worker 的 /chat（CHAT_URL，用 RELAY_TOKEN 驗證），
   再把答案回覆在 Discord。模型、每人每天的次數上限都在 Worker 那邊，和 /ask 一樣。

注意：
- 不要在這裡建立或同步任何指令（不用 app_commands / tree.sync），否則會蓋掉
  Worker 註冊的指令。指令的事件也不會送到這裡：後台設了 Interactions Endpoint URL，
  Discord 會把它們送到 Worker。
- 讀訊息內容要在 Discord 開發者後台打開 Message Content Intent。沒打開時會自動
  改用不含它的連線：@小花火、以及有提及小花火的回覆（Discord 回覆預設會提及）
  仍然讀得到內容，只有關掉提及的回覆會被略過。
- 沒設定 DISCORD_TOKEN（Render 上的 HANABI_DISCORD_TOKEN）時就安靜等待，
  不要結束：supervisor 會在程式結束 5 秒後重啟，會變成一直重啟。CHAT_URL /
  RELAY_TOKEN 沒設定時只顯示綠點、不聊天。
"""
import os
import re
import time

import aiohttp
import discord

TOKEN = os.getenv("DISCORD_TOKEN")
CHAT_URL = os.getenv("CHAT_URL")          # https://hanabi-discord.….workers.dev/chat
RELAY_TOKEN = os.getenv("RELAY_TOKEN")    # 和 Worker 的 secret RELAY_TOKEN 一樣
HISTORY = 8                               # 往上帶幾則對話給 AI
MAX_TEXT = 1000


def message_text(msg):
    """一則訊息的文字：內容，或 /ask 回答的 embed（引用的問題 + 答案）。"""
    text = msg.content or ""
    if not text and msg.embeds:
        e = msg.embeds[0]
        text = "\n".join(x for x in (e.title or "", e.description or "") if x)
    return text.strip()[:MAX_TEXT]


class Hanabi(discord.Client):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.http_session = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90))

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def on_ready(self):
        chat = "可以聊天" if CHAT_URL and RELAY_TOKEN else "沒有設定 CHAT_URL / RELAY_TOKEN，只顯示綠點"
        print(f"[hanabi_presence] 已上線：{self.user}（{len(self.guilds)} 個伺服器，{chat}）", flush=True)

    def addressed(self, msg):
        """這則訊息是對小花火說的嗎：回覆她的訊息，或 @她（不含 @everyone）。"""
        ref = msg.reference.resolved if msg.reference else None
        if isinstance(ref, discord.Message) and ref.author.id == self.user.id:
            return True
        return self.user in msg.mentions

    async def chain(self, msg):
        """這串回覆，由舊到新：[{role, text}]。"""
        out, cur = [], msg
        for _ in range(HISTORY):
            # 去掉 @小花火 本身
            text = re.sub(rf"<@!?{self.user.id}>", "", message_text(cur)).strip()
            if text:
                out.append({"role": "model" if cur.author.id == self.user.id else "user", "text": text})
            if not cur.reference or not cur.reference.message_id:
                break
            nxt = cur.reference.resolved if isinstance(cur.reference.resolved, discord.Message) else None
            if nxt is None:
                try:
                    nxt = await cur.channel.fetch_message(cur.reference.message_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    break
            cur = nxt
        return list(reversed(out))

    async def on_message(self, msg):
        if msg.author.bot or not CHAT_URL or not RELAY_TOKEN or not self.addressed(msg):
            return
        history = await self.chain(msg)
        if not history or history[-1]["role"] != "user":
            return
        locale = str(msg.guild.preferred_locale) if msg.guild else ""
        async with msg.channel.typing():
            try:
                async with self.http_session.post(
                    CHAT_URL,
                    json={"user": str(msg.author.id), "history": history, "locale": locale},
                    headers={"Authorization": f"Bearer {RELAY_TOKEN}"},
                ) as res:
                    if res.status != 200:
                        print(f"[hanabi_presence] /chat 回應 {res.status}", flush=True)
                        return
                    reply = (await res.json()).get("reply", "")
            except (aiohttp.ClientError, TimeoutError) as err:
                print(f"[hanabi_presence] /chat 失敗：{err}", flush=True)
                return
        # Discord 一則訊息最多 2000 字：太長就分段
        for i in range(0, len(reply), 1990):
            part = reply[i:i + 1990]
            if i == 0:
                await msg.reply(part, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            else:
                await msg.channel.send(part, allowed_mentions=discord.AllowedMentions.none())


def run(message_content):
    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.dm_messages = True
    intents.message_content = message_content
    client = Hanabi(intents=intents, status=discord.Status.online, activity=discord.Game(name="單字庫"))
    client.run(TOKEN, log_handler=None)


def main():
    if not TOKEN:
        print("[hanabi_presence] 沒有設定 HANABI_DISCORD_TOKEN，先不上線", flush=True)
        while True:
            time.sleep(3600)
    try:
        run(message_content=True)
    except discord.PrivilegedIntentsRequired:
        print("[hanabi_presence] Message Content Intent 沒有在開發者後台打開，改成只處理有提及小花火的訊息", flush=True)
        run(message_content=False)


if __name__ == "__main__":
    main()
