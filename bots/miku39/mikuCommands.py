# mikuCommands.py
import discord
from discord import app_commands
import random
import json
import os
import requests
from googleSearch import BEAUTY_IMAGES

import firebase_admin
from firebase_admin import credentials, db
from ossapi import Ossapi

DATA_FILE = "userPools.json"

# --- 自動拓圖（選用功能）：bot 抽卡 除了原本手動精選的 BEAUTY_IMAGES，也會有機率
# 即時從 Safebooru（純 SFW 的動漫圖庫鏡像，rating 一定過濾為 safe）隨機抓一張新圖，
# 不限定特定角色/作品，圖庫非常龐大不容易抽到重複的。抓取失敗（逾時/斷線/API 改版）
# 就直接回傳 None，呼叫端會自動退回使用 BEAUTY_IMAGES，不影響 bot 抽卡 的核心功能。
SAFEBOORU_API = "https://safebooru.org/index.php"
SAFEBOORU_TAGS = "1girl solo"
SAFEBOORU_PID_RANGE = 3000  # 實測這個 tag 組合在 pid=8000 仍有結果，這裡保守取值避免抽到空頁

def fetch_random_anime_image():
    """從 Safebooru 隨機抓一張 SFW 動漫圖的網址，失敗回傳 None"""
    try:
        pid = random.randint(0, SAFEBOORU_PID_RANGE)
        resp = requests.get(SAFEBOORU_API, params={
            "page": "dapi", "s": "post", "q": "index", "json": "1",
            "tags": SAFEBOORU_TAGS, "pid": pid, "limit": 1,
        }, timeout=8, headers={"User-Agent": "Miku39-DiscordBot/1.0"})
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        post = data[0]
        # Safebooru 混用新舊兩套 rating 命名："general"（新的 4 級制，等同全年齡）
        # 跟 "safe"（舊的 3 級制），兩者都算安全，混合式命名是它自己 API 的行為
        if post.get("rating") not in ("general", "safe"):
            return None
        return post.get("file_url") or post.get("sample_url")
    except Exception as e:
        print(f"[MIKU39] Safebooru 抓圖失敗（將改用精選圖庫）: {e}")
        return None

# --- osu! 戰績串接（選用功能）：讀取 Osu Bot 寫進同一個 Firebase 的帳號綁定／排名
# 資料（見 osu_bot/cogs/osu_commands.py 的 !link、!profile 排名追蹤），讓「bot 運勢」
# 的抽籤結果偷偷參考最近的 osu! 排名升降。任何一步失敗（沒設定 Firebase/osu API 憑證、
# 使用者沒綁定、查詢失敗...）都直接停用這個功能、退回完全隨機抽籤，不會影響 MIKU39
# 原本的抽籤/抽卡/珍藏庫功能。
_osu_api = None
try:
    if not firebase_admin._apps:
        _env_creds = os.getenv("FIREBASE_CREDENTIALS")
        if _env_creds:
            _cred = credentials.Certificate(json.loads(_env_creds))
            firebase_admin.initialize_app(_cred, {
                'databaseURL': 'https://osu-discord-bot-56c1d-default-rtdb.firebaseio.com/'
            })
    _client_id = os.getenv("OSU_CLIENT_ID")
    _client_secret = os.getenv("OSU_CLIENT_SECRET")
    if firebase_admin._apps and _client_id and _client_secret:
        _osu_api = Ossapi(int(_client_id), _client_secret)
except Exception as e:
    print(f"[MIKU39] osu! 戰績串接初始化失敗（將以純隨機運勢繼續運作）: {e}")
    _osu_api = None

# --- 精選圖庫的線上新增功能：BEAUTY_IMAGES 是寫死在程式碼裡的固定清單，改它需要
# 重新部署才會生效，所以新增的圖另外存進 Firebase（跟 osu! 戰績串接共用同一個
# database，初始化流程見上面），bot 抽卡 時把兩份清單合併抽選，加圖立即生效。
CUSTOM_IMAGES_PATH = 'miku_gacha/custom_images'

def get_custom_images():
    if not firebase_admin._apps:
        return []
    try:
        data = db.reference(CUSTOM_IMAGES_PATH).get()
        return data or []
    except Exception as e:
        print(f"[MIKU39] 讀取精選圖庫（Firebase）失敗: {e}")
        return []

def save_custom_images(images):
    db.reference(CUSTOM_IMAGES_PATH).set(images)

def load_user_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_user_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# 🎲 7種運勢抽籤
FORTUNE_LIST = [
    {"type": "🌟 大吉", "desc": "今天打 osu! 的節奏感就像世界第一公主殿下一樣完美！適合去刷 pp 喔！", "gif": "https://s1.aigei.com/src/img/gif/16/1644ae8483424bfc9c17c770c3d82301.gif"},
    {"type": "✨ 中吉", "desc": "今天狀態不錯呢♪ 稍微挑戰一下平常打不過的圖，說不定能輕鬆 FC 唷！", "gif": "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif"},
    {"type": "🍀 小吉", "desc": "平穩的一天。泡杯蔥茶，輕鬆地享受幾首經典的 VOCALOID 曲目吧！", "gif": "https://i.pinimg.com/originals/1d/4c/ca/1d4cca014fe631c1a8a7e8a59e4263b2.gif"},
    {"type": "💠 末吉", "desc": "稍微有一點點容易掉 point... 打歌前記得先做一下手指拉伸運動喔！", "gif": "https://i.pinimg.com/originals/d9/e4/d0/d9e4d0064938e822c79614936fbf9ffc.gif"},
    {"type": "⛅ 吉", "desc": "普通的一天，今天的 Miku 也在默默幫你加油，踏實地練習吧！", "gif": "https://i.makeagif.com/media/4-01-2023/E9l_XP.gif"},
    {"type": "💧 凶", "desc": "今天可能會遇到音壓怪或者瘋狂 Miss... 沒關係，早點休息，明天又是新的一天！", "gif": "https://s1.aigei.com/src/img/gif/16/1644ae8483424bfc9c17c770c3d82301.gif"},
    {"type": "⚡ 大凶", "desc": "嗚哇！今天打歌手感不太對勁呢... 快去吃碗大蔥拉麵補充元氣，今天先別強求 pp 了！", "gif": "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif"}
]

# FORTUNE_LIST 索引對應的好/壞籤（依內容描述分類，不是單純依序排列——
# 「末吉」描述偏負面，「吉」描述偏正常/正面，所以它們的順序跟字面吉凶不完全一致）
_GOOD_FORTUNE_INDICES = {0, 1, 2, 4}   # 大吉、中吉、小吉、吉
_BAD_FORTUNE_INDICES = {3, 5, 6}       # 末吉、凶、大凶

def _get_luck_bias(user_id):
    """查詢該使用者最近的 osu! 全球排名變化（跟 Osu Bot 的 !profile 共用同一份
    Firebase last_rank 記錄）。回傳 'up'／'down'／None，None 代表沒綁定、
    Osu Bot 那邊還沒有比較基準、或查詢失敗——這幾種情況都維持完全隨機抽籤。"""
    if not _osu_api:
        return None
    try:
        user_data = db.reference(f'users/{user_id}').get()
        if not user_data or not user_data.get('osu_name'):
            return None
        prev_rank = db.reference(f'users/{user_id}/last_rank/osu').get()
        if not isinstance(prev_rank, int):
            return None
        user = _osu_api.user(user_data['osu_name'], mode='osu', key='username')
        if not user.statistics or user.statistics.global_rank is None:
            return None
        current_rank = user.statistics.global_rank
        if current_rank < prev_rank:
            return 'up'
        if current_rank > prev_rank:
            return 'down'
        return None
    except Exception:
        return None

def _pick_fortune(bias):
    if bias == 'up':
        weights = [3 if i in _GOOD_FORTUNE_INDICES else 1 for i in range(len(FORTUNE_LIST))]
        return random.choices(FORTUNE_LIST, weights=weights, k=1)[0]
    if bias == 'down':
        weights = [3 if i in _BAD_FORTUNE_INDICES else 1 for i in range(len(FORTUNE_LIST))]
        return random.choices(FORTUNE_LIST, weights=weights, k=1)[0]
    return random.choice(FORTUNE_LIST)

# 🗂️ 珍藏庫互動按鈕 View 類別（含刪除功能）
class PoolView(discord.ui.View):
    def __init__(self, author_id, card_list):
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.card_list = card_list
        self.current_index = 0

    def get_embed(self):
        embed = discord.Embed(
            title=f"💚 你的專屬美圖珍藏庫 ({self.current_index + 1}/{len(self.card_list)})",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=self.card_list[self.current_index])
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 這是別人的珍藏庫，不能幫他翻頁或操作唷！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="◀️ 上一張", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = len(self.card_list) - 1 if self.current_index == 0 else self.current_index - 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    # 🗑️ 新增的移除按鈕
    @discord.ui.button(label="🗑️ 移除這張", style=discord.ButtonStyle.danger)
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        removed_url = self.card_list[self.current_index]
        
        # 從內存的卡片列表中移除
        self.card_list.remove(removed_url)
        
        # 同步更新 JSON 檔案
        data = load_user_data()
        uid = str(self.author_id)
        if uid in data and removed_url in data[uid]:
            data[uid].remove(removed_url)
            save_user_data(data)
            
        # 檢查刪除後是否還有剩下圖片
        if not self.card_list:
            # 沒圖片了，直接更新為空空如也的狀態，並移除按鈕
            await interaction.response.edit_message(content="💨 你的珍藏庫已經被清空囉！", embed=None, view=None)
            return

        # 如果還有圖片，調整 index 避免溢出
        if self.current_index >= len(self.card_list):
            self.current_index = 0
            
        # 刷新畫面，並用臨時回應通知使用者刪除成功
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
        await interaction.followup.send("💚 已成功從你的珍藏庫移除該圖片♪", ephemeral=True)

    @discord.ui.button(label="▶️ 下一張", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = 0 if self.current_index == len(self.card_list) - 1 else self.current_index + 1
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

# 🎁 抽卡結果的「收藏」按鈕 View（抽到的圖不管來自精選圖庫還是即時抓的新圖都共用同一套）
class CollectView(discord.ui.View):
    def __init__(self, url):
        super().__init__(timeout=60.0)
        self.url = url

    @discord.ui.button(label="💖 收藏這張美圖", style=discord.ButtonStyle.success)
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = str(interaction.user.id)
        data = load_user_data()
        if uid not in data:
            data[uid] = []
        if self.url in data[uid]:
            await interaction.response.send_message("✨ 這張圖已經在你的珍藏庫裡囉！", ephemeral=True)
        else:
            data[uid].append(self.url)
            save_user_data(data)
            await interaction.response.send_message("💖 成功將美圖收藏至你的個人珍藏庫！", ephemeral=True)


def register_commands(bot):
    """把 MIKU39 的指令註冊到 bot 上——用 hybrid_command 讓每個指令同時支援
    原本的 `bot 指令名` 文字前綴跟新的 `/指令名` Slash 介面，兩種叫法共用同一份邏輯。"""

    @bot.hybrid_command(name="運勢", description="抽一次今日運勢籤詩")
    async def fortune_command(ctx):
        bias = _get_luck_bias(str(ctx.author.id))
        fortune = _pick_fortune(bias)
        embed = discord.Embed(
            title=f"🎤 Miku39 占卜結果：{fortune['type']}",
            description=fortune['desc'],
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=fortune['gif'])
        if bias == 'up':
            embed.set_footer(text="💫 偵測到你最近 osu! 排名進步了，運勢也跟著沾光～")
        elif bias == 'down':
            embed.set_footer(text="😮‍💨 偵測到你最近 osu! 排名有點退步，Miku 悄悄幫你加油中...")
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="抽卡", description="隨機抽一張美圖，可以收藏到珍藏庫")
    async def gacha_command(ctx):
        # 一半機率嘗試即時從網路抓一張新圖，抓不到（逾時/斷線）就退回精選圖庫，
        # 確保這個指令永遠不會因為外部 API 問題而完全失敗
        img_url = fetch_random_anime_image() if random.random() < 0.5 else None
        if not img_url:
            curated_pool = BEAUTY_IMAGES + get_custom_images()
            img_url = random.choice(curated_pool)
        embed = discord.Embed(
            title="🎤 世界第一公主殿下 美圖抽卡 ♪",
            description="點擊按鈕或輸入指令可以收藏到珍藏庫喔！",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=img_url)
        await ctx.send(embed=embed, view=CollectView(img_url))

    @bot.hybrid_command(name="珍藏庫", description="翻看你收藏的美圖")
    async def collection_command(ctx):
        data = load_user_data()
        user_cards = data.get(str(ctx.author.id), [])

        if not user_cards:
            await ctx.send("💨 你的珍藏庫目前空空如也呢！快使用 `/抽卡` 來收集公主殿下的美圖吧！")
            return

        view = PoolView(ctx.author.id, user_cards)
        await ctx.send(embed=view.get_embed(), view=view)

    @bot.hybrid_command(name="加圖", description="（僅限主人）新增一張圖片網址到精選圖庫")
    @app_commands.describe(url="圖片網址（需以 http:// 或 https:// 開頭）")
    async def add_image_command(ctx, url: str):
        owner_id = os.getenv("MIKU_OWNER_ID")
        if not owner_id or str(ctx.author.id) != owner_id:
            await ctx.send("❌ 只有小天地主人才能新增精選圖庫喔！")
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            await ctx.send("❌ 這不是一個有效的網址（必須以 http:// 或 https:// 開頭）")
            return
        if not firebase_admin._apps:
            await ctx.send("❌ Firebase 尚未設定好，暫時無法新增圖庫（不影響現有的 /抽卡）。")
            return

        custom_images = get_custom_images()
        if url in BEAUTY_IMAGES or url in custom_images:
            await ctx.send("⚠️ 這張圖片網址已經在精選圖庫裡囉！")
            return

        custom_images.append(url)
        save_custom_images(custom_images)
        total = len(BEAUTY_IMAGES) + len(custom_images)
        await ctx.send(f"💚 成功加入精選圖庫！（目前精選圖庫共 {total} 張，立即生效）")

    @bot.hybrid_command(name="選單", aliases=["help", "指令"], description="顯示 MIKU39 的指令說明")
    async def menu_command(ctx):
        embed = discord.Embed(
            title="🎤 MIKU39 指令選單",
            description="以下是目前可以使用的指令：\n──────────────────",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.add_field(name="`/運勢`", value="抽一次今日運勢籤詩（如果你已經在 Osu Bot 用過 `/link` 綁定帳號，運勢會偷偷參考你最近的 osu! 排名升降喔）", inline=False)
        embed.add_field(name="`/抽卡`", value="隨機抽一張美圖（精選圖庫 + 一定機率即時從網路抓新圖），可以收藏到珍藏庫", inline=False)
        embed.add_field(name="`/珍藏庫`", value="翻看你收藏的美圖，可以上一張／下一張／移除", inline=False)
        owner_id = os.getenv("MIKU_OWNER_ID")
        if owner_id and str(ctx.author.id) == owner_id:
            embed.add_field(name="`/加圖 [網址]`", value="（僅限主人）把新的圖片網址加進精選圖庫，立即生效不用重新部署", inline=False)
        embed.set_footer(text="💚 想再看一次這份選單，隨時輸入 /選單 或 bot 選單")
        await ctx.send(embed=embed)