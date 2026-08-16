# mikuCommands.py
import discord
from discord import app_commands
import random
import json
import os
import requests
from datetime import datetime, timedelta, timezone
from googleSearch import BEAUTY_IMAGES
from calendar_render import render_checkin_calendar
from payslip_render import render_payslip

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

# --- Firebase 初始化：注意這裡不是只影響下面的 osu! 戰績串接（選用功能）——
# 這是整個檔案唯一一處呼叫 firebase_admin.initialize_app() 的地方，抽卡保底、
# 精選圖庫、珍藏庫、好感度/EXP、每日運勢、簽到、打工全部都靠 firebase_admin._apps
# 是否非空來決定要不要真的讀寫資料庫（各自的 _get_*/_save_* 開頭都有
# `if not firebase_admin._apps: return`）。如果 Render 上 miku39 這支子程序沒有
# 拿到 FIREBASE_CREDENTIALS，上面全部功能都會「指令照樣能跑、但資料完全不會被
# 存起來」——不會噴錯，畫面上也不會有任何提示，只能從這裡的 log 看出來，所以
# 「找不到憑證」這個分支特別印一行明顯的警告，不要跟下面 try/except 只印例外訊息
# 的寫法混在一起、一聲不響就跳過。
_osu_api = None
try:
    if not firebase_admin._apps:
        _env_creds = os.getenv("FIREBASE_CREDENTIALS")
        if _env_creds:
            _cred = credentials.Certificate(json.loads(_env_creds))
            firebase_admin.initialize_app(_cred, {
                'databaseURL': 'https://osu-discord-bot-56c1d-default-rtdb.firebaseio.com/'
            })
            print("[MIKU39] Firebase 初始化成功，抽卡/珍藏庫/簽到/打工等持久化功能已啟用")
        else:
            print("[MIKU39] 警告：找不到 FIREBASE_CREDENTIALS 環境變數！"
                  "抽卡保底、精選圖庫、珍藏庫、好感度、運勢、簽到、打工全部都不會存檔"
                  "（指令仍然能執行，只是資料存不進去，重啟就消失）")

    # osu! 戰績串接才是真的「選用功能」：讀取 Osu Bot 寫進同一個 Firebase 的帳號
    # 綁定／排名資料（見 osu_bot/cogs/osu_commands.py 的 !link、!profile 排名追蹤），
    # 讓「/運勢」的抽籤結果偷偷參考最近的 osu! 排名升降。沒設定 osu API 憑證、
    # 使用者沒綁定、查詢失敗都只會讓這個小彩蛋停用、退回完全隨機抽籤，不影響上面
    # 任何一個持久化功能。
    _client_id = os.getenv("OSU_CLIENT_ID")
    _client_secret = os.getenv("OSU_CLIENT_SECRET")
    if firebase_admin._apps and _client_id and _client_secret:
        _osu_api = Ossapi(int(_client_id), _client_secret)
except Exception as e:
    print(f"[MIKU39] Firebase／osu! 戰績串接初始化失敗: {e}")
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

# --- 抽卡保底機制：參考常見 gacha bot（如 Genshin 抽卡模擬器）的 pity system，
# 連續 GACHA_PITY_THRESHOLD 次都沒抽到精選圖庫的圖時，下一抽直接保底送上精選圖。
# 保底次數存 Firebase（跨 Render 重新部署不會遺失），任何一步失敗都視為 0 次，
# 頂多保底沒生效，不影響 /抽卡 本身能不能抽。
GACHA_PITY_PATH = 'miku_gacha/pity'
GACHA_PITY_THRESHOLD = 5

# --- 抽卡稀有度分級：把「抽不抽得到精選圖」包裝成正式的稀有度階級，抽卡的爽感
# 通常來自於知道自己抽到什麼等級，而不只是有沒有中。沿用現有的兩個圖庫，不用
# 準備新素材：
#   N（普通）：即時從 Safebooru 抓的隨機圖，範圍最廣、機率最高
#   R（稀有）：BEAUTY_IMAGES，寫死在程式碼裡的精選圖庫
#   SR（超稀有）：custom_images，主人透過 /加圖 額外新增的圖，通常數量少、更特別
# 保底機制不變（依然保證不會抽到 N），R／SR 之間再依固定權重抽一次。
GACHA_TIER_COLORS = {"N": "#9CA3AF", "R": "#60A5FA", "SR": "#C084FC"}
GACHA_TIER_LABELS = {"N": "⚪ N", "R": "🔵 R", "SR": "🟣 SR"}
GACHA_SR_CHANCE = 0.3  # 抽到「精選圖庫」時，有 30% 機率是 SR（custom_images），其餘是 R

def _get_pity_count(user_id):
    if not firebase_admin._apps:
        return 0
    try:
        return db.reference(f'{GACHA_PITY_PATH}/{user_id}').get() or 0
    except Exception as e:
        print(f"[MIKU39] 讀取保底次數失敗: {e}")
        return 0

def _set_pity_count(user_id, count):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{GACHA_PITY_PATH}/{user_id}').set(count)
    except Exception as e:
        print(f"[MIKU39] 更新保底次數失敗: {e}")

def _today_str():
    # 用 UTC 日期當「一天」的邊界，簡單一致就好，不用特別對齊使用者時區
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

def _yesterday_str():
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

# --- 每日簽到／連續天數：獨立於好感度等級之外的另一條每日習慣，中斷一天就
# 從第 1 天重新算起。連續簽到的經驗值獎勵會遞增，但有上限，不會無止盡疊加。
CHECKIN_PATH = 'miku_gacha/checkin'
CHECKIN_BASE_EXP = 5
CHECKIN_STREAK_EXP_CAP = 15
CHECKIN_MILESTONE_DAYS = 7

def _get_checkin_data(user_id):
    if not firebase_admin._apps:
        return None
    try:
        return db.reference(f'{CHECKIN_PATH}/{user_id}').get()
    except Exception as e:
        print(f"[MIKU39] 讀取簽到資料失敗: {e}")
        return None

def _save_checkin(user_id, date_str, streak):
    if not firebase_admin._apps:
        return
    try:
        # .update() 而不是 .set()，這樣才不會把 dates 底下累積的簽到歷史一起蓋掉——
        # set() 是整個節點覆寫，update() 才是只改指定的幾個 key，'dates/xxx' 這種
        # 帶斜線的 key 是 Firebase Admin SDK 支援的巢狀路徑寫法。
        db.reference(f'{CHECKIN_PATH}/{user_id}').update({
            'date': date_str,
            'streak': streak,
            f'dates/{date_str}': True,
        })
    except Exception as e:
        print(f"[MIKU39] 更新簽到資料失敗: {e}")

def _get_checked_dates(user_id):
    """回傳這個使用者「所有」簽到過的日期字串集合（給行事曆畫圖用，呼叫端
    自己篩選要哪個月份）。"""
    data = _get_checkin_data(user_id)
    if not data:
        return set()
    return set((data.get('dates') or {}).keys())

# --- 好感度／羈絆等級系統：把 /運勢、/抽卡 這些互動串成一條養成線，每次使用
# 都會累積經驗值，升級解鎖額外內容。等級公式用固定每級 EXP_PER_LEVEL 點經驗
# （簡單好懂，/好感度 顯示進度條也方便）。
AFFINITY_PATH = 'miku_gacha/affinity'
EXP_PER_LEVEL = 100
FORTUNE_EXP = 5
GACHA_EXP = 3

AFFINITY_UNLOCKS = [
    (5, "🔮 隱藏籤詩"),
    (10, "🎯 抽卡保底門檻降低 1 次"),
    (20, "🎁 每日抽卡上限 +3"),
    (39, "💫 特殊稱號＋隱藏彩蛋"),
]

def _get_exp(user_id):
    if not firebase_admin._apps:
        return 0
    try:
        return db.reference(f'{AFFINITY_PATH}/{user_id}').get() or 0
    except Exception as e:
        print(f"[MIKU39] 讀取好感度失敗: {e}")
        return 0

def _add_exp(user_id, amount):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{AFFINITY_PATH}/{user_id}').set(_get_exp(user_id) + amount)
    except Exception as e:
        print(f"[MIKU39] 更新好感度失敗: {e}")

def _level_from_exp(exp):
    return exp // EXP_PER_LEVEL + 1

def _pity_threshold_for_level(level):
    return GACHA_PITY_THRESHOLD - 1 if level >= 10 else GACHA_PITY_THRESHOLD

def _gacha_daily_limit_for_level(level):
    return GACHA_DAILY_LIMIT + 3 if level >= 20 else GACHA_DAILY_LIMIT

# --- /運勢 每日限抽一次：不然「今日運勢」的「今日」就沒意義了，也順便堵住
# 用它無限刷好感度經驗值的漏洞。存的是完整籤詩內容（不只索引），這樣同一天
# 重複查詢可以原封不動地重新顯示同一份結果。
DAILY_FORTUNE_PATH = 'miku_gacha/daily_fortune'

def _get_saved_fortune(user_id):
    if not firebase_admin._apps:
        return None
    try:
        data = db.reference(f'{DAILY_FORTUNE_PATH}/{user_id}').get()
        if data and data.get('date') == _today_str():
            return data.get('fortune')
        return None
    except Exception as e:
        print(f"[MIKU39] 讀取今日運勢失敗: {e}")
        return None

def _save_today_fortune(user_id, fortune):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{DAILY_FORTUNE_PATH}/{user_id}').set({'date': _today_str(), 'fortune': fortune})
    except Exception as e:
        print(f"[MIKU39] 儲存今日運勢失敗: {e}")

# --- /抽卡 每日次數上限：原本完全沒有限制、可以無限狂抽，好感度系統上線後
# 如果不擋，會變成靠瘋狂抽卡就能無限刷經驗值、失去升級的意義。
GACHA_DAILY_LIMIT = 10
DAILY_DRAWS_PATH = 'miku_gacha/daily_draws'

def _get_daily_draw_count(user_id):
    if not firebase_admin._apps:
        return 0
    try:
        data = db.reference(f'{DAILY_DRAWS_PATH}/{user_id}').get()
        if data and data.get('date') == _today_str():
            return data.get('count', 0)
        return 0
    except Exception as e:
        print(f"[MIKU39] 讀取每日抽卡次數失敗: {e}")
        return 0

def _increment_daily_draw_count(user_id, current_count):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{DAILY_DRAWS_PATH}/{user_id}').set({'date': _today_str(), 'count': current_count + 1})
    except Exception as e:
        print(f"[MIKU39] 更新每日抽卡次數失敗: {e}")

# --- 珍藏庫（每位使用者收藏的美圖清單）：原本存在本機的 userPools.json，
# Render 免費方案的容器磁碟是 ephemeral 的，重新部署一次舊資料就整個消失。
# 改存 Firebase，per-user 一個路徑，跟保底次數/精選圖庫用同一顆資料庫，
# 讀寫都只動單一使用者的節點，不用像本機版那樣每次都整包讀寫所有人的資料。
COLLECTIONS_PATH = 'miku_gacha/collections'

def get_user_collection(user_id):
    if not firebase_admin._apps:
        return []
    try:
        data = db.reference(f'{COLLECTIONS_PATH}/{user_id}').get()
        return data or []
    except Exception as e:
        print(f"[MIKU39] 讀取珍藏庫失敗: {e}")
        return []

def save_user_collection(user_id, images):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{COLLECTIONS_PATH}/{user_id}').set(images)
    except Exception as e:
        print(f"[MIKU39] 更新珍藏庫失敗: {e}")

def _collection_progress(user_cards):
    """圖鑑收集度：只算「精選圖庫」(R+SR，BEAUTY_IMAGES + custom_images) 這個
    固定名單，N 那種即時從網路抓的隨機圖沒有邊界、不算進總數裡，不然永遠湊
    不齊。回傳 (已收集數, 精選圖庫總數)。"""
    curated_pool = set(BEAUTY_IMAGES) | set(get_custom_images())
    collected = len(set(user_cards) & curated_pool)
    return collected, len(curated_pool)

# --- 每日打工：跟 /簽到 一樣是每天限一次的額外好感度經驗值來源，但沒有連續
# 天數加成，單純就是「今天做過了沒」。每次打工會隨機分配到一份工作，並附上
# 一張視覺化薪資單（跟 /簽到 的行事曆一樣走「附一張圖」的路線）；還有機率
# 觸發特殊事件（加班費／驚喜禮物／扣薪），讓每天的結果不會一成不變。
WORK_PATH = 'miku_gacha/work'

WORK_JOBS = [
    {
        "emoji": "🎸", "name": "演唱會場務", "label": "Stagehand",
        "exp_range": (4, 7),
        "messages": [
            "去 livehouse 打工搬音響，賺到了一些好感度經驗值！🎸",
            "幫忙架設演唱會舞台燈光，累但很有成就感！💡",
        ],
    },
    {
        "emoji": "🎧", "name": "錄音室助理", "label": "Studio Assistant",
        "exp_range": (5, 8),
        "messages": [
            "幫忙錄音室調音一整天，Miku 對你刮目相看～🎧",
            "整理錄音室的樂譜和器材，意外發現了一段沒公開過的旋律！🎼",
        ],
    },
    {
        "emoji": "🧅", "name": "周邊攤位店員", "label": "Merch Stall",
        "exp_range": (3, 6),
        "messages": [
            "在演唱會賣周邊商品，跟粉絲聊得很開心！🎤",
            "顧攤位賣蔥造型周邊，業績嚇嚇叫！🧅",
        ],
    },
    {
        "emoji": "📻", "name": "電台助理", "label": "Radio Assistant",
        "exp_range": (4, 8),
        "messages": [
            "在電台幫忙選歌、接聽點歌，跟聽眾們相談甚歡！📻",
            "幫電台節目寫了一段開場稿，主持人稱讚超順口！🎙️",
        ],
    },
    {
        "emoji": "✍️", "name": "作詞企劃", "label": "Lyricist",
        "exp_range": (5, 9),
        "messages": [
            "幫 Miku 寫了一段新歌詞，靈感被稱讚了一番！🎶",
            "跟企劃團隊一起腦力激盪新曲主題，討論到欲罷不能！💭",
        ],
    },
]

# 特殊事件：每次打工有 WORK_EVENT_CHANCE 的機率額外觸發一個，觸發後再依權重
# 抽出是哪一種。bonus_image 如果精選圖庫剛好被抽爆、連即時抓圖也失敗，就當
# 這次事件沒發生（不影響打工本身能不能領到底薪）。
WORK_EVENT_CHANCE = 0.3
WORK_EVENTS = [
    {
        "type": "bonus_exp", "weight": 45,
        "label_zh": "🎉 加班費", "label_en": "Overtime Bonus",
        "exp_range": (3, 8),
        "flavor": "工作表現太亮眼，臨時被加碼了一筆獎金！",
    },
    {
        "type": "bonus_image", "weight": 25,
        "label_zh": "🎁 意外驚喜", "label_en": "Surprise Gift",
        "flavor": "打工途中意外收到一份神秘禮物！",
    },
    {
        "type": "penalty", "weight": 30,
        "label_zh": "😴 手忙腳亂", "label_en": "Rough Shift",
        "exp_range": (2, 5),
        "flavor": "今天狀況有點多，不小心被扣了一點薪水...",
    },
]

def _get_last_work_date(user_id):
    if not firebase_admin._apps:
        return None
    try:
        return db.reference(f'{WORK_PATH}/{user_id}').get()
    except Exception as e:
        print(f"[MIKU39] 讀取打工紀錄失敗: {e}")
        return None

def _save_work_date(user_id, date_str):
    if not firebase_admin._apps:
        return
    try:
        db.reference(f'{WORK_PATH}/{user_id}').set(date_str)
    except Exception as e:
        print(f"[MIKU39] 更新打工紀錄失敗: {e}")

def _migrate_local_collections_to_firebase():
    """一次性搬遷：如果容器裡還留著舊版的 userPools.json，且 Firebase 那邊的
    珍藏庫路徑目前是空的，就把本機資料搬過去，避免這次改版直接把使用者手上
    的珍藏庫歸零。搬完之後這個檔案就不會再被讀寫，可以安全刪除。"""
    if not firebase_admin._apps or not os.path.exists(DATA_FILE):
        return
    try:
        if db.reference(COLLECTIONS_PATH).get():
            return  # Firebase 已經有資料了，不要覆蓋
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            local_data = json.load(f)
        if local_data:
            db.reference(COLLECTIONS_PATH).set(local_data)
            print(f"[MIKU39] 已將本機珍藏庫資料（{len(local_data)} 位使用者）搬遷至 Firebase")
    except Exception as e:
        print(f"[MIKU39] 珍藏庫資料搬遷失敗: {e}")

_migrate_local_collections_to_firebase()

# 🎲 7種運勢抽籤
# GIF 來源說明：s1.aigei.com 那個網址已經失效（實測回傳 401 Unauthorized），原本
# 用在 大吉／凶／羈絆吉 三個地方，全部是壞圖。makeagif 那個雖然還活著但檔案有
# 8MB，對一個常常會被抽到的訊息來說太重。這裡全部換成驗證過能直接嵌入、且
# 確實是初音未來本人的 GIF（c.tenor.com 那三個是 Tenor 的直連 CDN 網址，用
# media.tenor.com/m/... 那種分享頁網址在 Discord 裡不會顯示圖片，記得只能用
# c.tenor.com/<id>/<檔名>.gif 這種格式）。
FORTUNE_LIST = [
    {"type": "🌟 大吉", "desc": "今天打 osu! 的節奏感就像世界第一公主殿下一樣完美！適合去刷 pp 喔！", "gif": "https://c.tenor.com/8JhcC4OtwC8AAAAC/hatsune-miku-dance.gif"},
    {"type": "✨ 中吉", "desc": "今天狀態不錯呢♪ 稍微挑戰一下平常打不過的圖，說不定能輕鬆 FC 唷！", "gif": "https://c.tenor.com/UYSDv3wnwhQAAAAC/hatsune-miku-dance.gif"},
    {"type": "🍀 小吉", "desc": "平穩的一天。泡杯蔥茶，輕鬆地享受幾首經典的 VOCALOID 曲目吧！", "gif": "https://i.pinimg.com/originals/1d/4c/ca/1d4cca014fe631c1a8a7e8a59e4263b2.gif"},
    {"type": "💠 末吉", "desc": "稍微有一點點容易掉 point... 打歌前記得先做一下手指拉伸運動喔！", "gif": "https://i.pinimg.com/originals/d9/e4/d0/d9e4d0064938e822c79614936fbf9ffc.gif"},
    {"type": "⛅ 吉", "desc": "普通的一天，今天的 Miku 也在默默幫你加油，踏實地練習吧！", "gif": "https://c.tenor.com/Jopqcgk8uyAAAAAC/hatsune-miku-miku-hatsune.gif"},
    {"type": "💧 凶", "desc": "今天可能會遇到音壓怪或者瘋狂 Miss... 沒關係，早點休息，明天又是新的一天！", "gif": "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif"},
    {"type": "⚡ 大凶", "desc": "嗚哇！今天打歌手感不太對勁呢... 快去吃碗大蔥拉麵補充元氣，今天先別強求 pp 了！", "gif": "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif"}
]

# 好感度 Lv.5 起解鎖的隱藏籤詩，混在一般籤詩池裡有機率額外抽到（見 _pick_fortune）
HIDDEN_FORTUNE_LIST = [
    {"type": "💚 羈絆吉", "desc": "跟 Miku 之間的默契已經培養起來了呢！今天不管打什麼曲子，感覺都會被溫柔地包圍著唷～", "gif": "https://c.tenor.com/8JhcC4OtwC8AAAAC/hatsune-miku-dance.gif"},
    {"type": "🎋 特別吉", "desc": "身為認識這麼久的老朋友，Miku 偷偷告訴你一個秘密：今天很適合挑戰個人最佳紀錄喔！", "gif": "https://c.tenor.com/UYSDv3wnwhQAAAAC/hatsune-miku-dance.gif"},
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

def _pick_fortune(bias, level=1):
    if bias == 'up':
        weights = [3 if i in _GOOD_FORTUNE_INDICES else 1 for i in range(len(FORTUNE_LIST))]
        result = random.choices(FORTUNE_LIST, weights=weights, k=1)[0]
    elif bias == 'down':
        weights = [3 if i in _BAD_FORTUNE_INDICES else 1 for i in range(len(FORTUNE_LIST))]
        result = random.choices(FORTUNE_LIST, weights=weights, k=1)[0]
    else:
        result = random.choice(FORTUNE_LIST)
    # 好感度 Lv.5 起，有機率把結果換成隱藏籤詩（不動原本的好/壞籤權重邏輯，
    # 純粹是抽完之後的一次額外覆蓋機會）
    if level >= 5 and random.random() < 0.15:
        result = random.choice(HIDDEN_FORTUNE_LIST)
    return result

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
        collected, total = _collection_progress(self.card_list)
        if total > 0:
            if collected >= total:
                embed.set_footer(text=f"🏆 圖鑑收集度：{collected}/{total}（全收集達成！）")
            else:
                embed.set_footer(text=f"📖 圖鑑收集度：{collected}/{total}")
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

        # 同步更新 Firebase
        save_user_collection(str(self.author_id), self.card_list)

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
        collection = get_user_collection(uid)
        if self.url in collection:
            await interaction.response.send_message("✨ 這張圖已經在你的珍藏庫裡囉！", ephemeral=True)
        else:
            collection.append(self.url)
            save_user_collection(uid, collection)
            await interaction.response.send_message("💖 成功將美圖收藏至你的個人珍藏庫！", ephemeral=True)


def register_commands(bot):
    """把 MIKU39 的指令註冊到 bot 上——用 hybrid_command 讓每個指令同時支援
    原本的 `bot 指令名` 文字前綴跟新的 `/指令名` Slash 介面，兩種叫法共用同一份邏輯。"""

    @bot.hybrid_command(name="運勢", description="抽一次今日運勢籤詩（每天限抽一次，重複查詢會顯示今天已抽過的結果）")
    async def fortune_command(ctx):
        uid = str(ctx.author.id)
        saved = _get_saved_fortune(uid)
        bias = None
        if saved is None:
            bias = _get_luck_bias(uid)
            level = _level_from_exp(_get_exp(uid))
            fortune = _pick_fortune(bias, level)
            _save_today_fortune(uid, fortune)
            _add_exp(uid, FORTUNE_EXP)
        else:
            fortune = saved

        embed = discord.Embed(
            title=f"🎤 Miku39 占卜結果：{fortune['type']}",
            description=fortune['desc'],
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=fortune['gif'])
        if saved is not None:
            embed.set_footer(text="📅 今天已經抽過囉，這是同一份結果～明天再來抽新的吧！")
        elif bias == 'up':
            embed.set_footer(text="💫 偵測到你最近 osu! 排名進步了，運勢也跟著沾光～")
        elif bias == 'down':
            embed.set_footer(text="😮‍💨 偵測到你最近 osu! 排名有點退步，Miku 悄悄幫你加油中...")
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="抽卡", description="隨機抽一張美圖（N/R/SR 稀有度），可以收藏到珍藏庫（每日有次數上限，連續沒中 R 以上會觸發保底）")
    async def gacha_command(ctx):
        uid = str(ctx.author.id)
        level = _level_from_exp(_get_exp(uid))
        daily_limit = _gacha_daily_limit_for_level(level)
        draw_count = _get_daily_draw_count(uid)

        if draw_count >= daily_limit:
            await ctx.send(f"💤 今天已經抽了 {draw_count} 次囉，明天再來吧！（今日上限：{daily_limit} 次，好感度 Lv.20 起上限會提升）")
            return

        pity_threshold = _pity_threshold_for_level(level)
        pity_count = _get_pity_count(uid)
        pity_triggered = pity_count + 1 >= pity_threshold

        # 保底還沒觸發時維持原本邏輯：一半機率嘗試即時從網路抓一張新圖，
        # 抓不到（逾時/斷線）就退回精選圖庫，確保這個指令永遠不會因為外部 API 問題而完全失敗
        img_url = None
        if not pity_triggered and random.random() < 0.5:
            img_url = fetch_random_anime_image()

        if img_url:
            tier = "N"
            pity_count += 1
            _set_pity_count(uid, pity_count)
        else:
            custom_images = get_custom_images()
            if custom_images and random.random() < GACHA_SR_CHANCE:
                tier = "SR"
                img_url = random.choice(custom_images)
            else:
                tier = "R"
                img_url = random.choice(BEAUTY_IMAGES)
            _set_pity_count(uid, 0)

        _increment_daily_draw_count(uid, draw_count)
        _add_exp(uid, GACHA_EXP)
        draws_used = draw_count + 1
        is_curated = tier != "N"

        embed = discord.Embed(
            title=f"🎤 世界第一公主殿下 美圖抽卡 ♪　{GACHA_TIER_LABELS[tier]}",
            description="點擊按鈕或輸入指令可以收藏到珍藏庫喔！",
            color=discord.Color.from_str(GACHA_TIER_COLORS[tier])
        )
        embed.set_image(url=img_url)
        if is_curated and pity_triggered:
            embed.set_footer(text=f"🌟 保底觸發！這次直接送上 {tier} 美圖～（保底進度已重置）今日抽卡：{draws_used}/{daily_limit}")
        elif is_curated:
            embed.set_footer(text=f"✨ {tier} 出貨！（保底進度已重置）今日抽卡：{draws_used}/{daily_limit}")
        else:
            embed.set_footer(text=f"🎲 保底進度：{pity_count}/{pity_threshold}　今日抽卡：{draws_used}/{daily_limit}")
        await ctx.send(embed=embed, view=CollectView(img_url))

    @bot.hybrid_command(name="珍藏庫", description="翻看你收藏的美圖")
    async def collection_command(ctx):
        user_cards = get_user_collection(str(ctx.author.id))

        if not user_cards:
            await ctx.send("💨 你的珍藏庫目前空空如也呢！快使用 `/抽卡` 來收集公主殿下的美圖吧！")
            return

        view = PoolView(ctx.author.id, user_cards)
        await ctx.send(embed=view.get_embed(), view=view)

    @bot.hybrid_command(name="贈送", description="把珍藏庫裡的一張圖送給其他人")
    @app_commands.describe(member="要贈送的對象", url="要送出的圖片網址（跟 /珍藏庫 裡看到的一樣）")
    async def gift_command(ctx, member: discord.Member, url: str):
        if member.id == ctx.author.id:
            await ctx.send("❌ 不能送給自己啦！")
            return
        if member.bot:
            await ctx.send("❌ 不能送給機器人喔！")
            return

        sender_id = str(ctx.author.id)
        sender_collection = get_user_collection(sender_id)
        if url not in sender_collection:
            await ctx.send("❌ 你的珍藏庫裡沒有這張圖，沒辦法送出去喔！（網址要跟 `/珍藏庫` 裡顯示的一模一樣）")
            return

        recipient_id = str(member.id)
        recipient_collection = get_user_collection(recipient_id)
        if url in recipient_collection:
            await ctx.send(f"⚠️ {member.mention} 已經有這張圖囉，不需要再送一次～")
            return

        sender_collection.remove(url)
        save_user_collection(sender_id, sender_collection)
        recipient_collection.append(url)
        save_user_collection(recipient_id, recipient_collection)

        embed = discord.Embed(
            title="🎁 贈送成功！",
            description=f"{ctx.author.mention} 把一張美圖送給了 {member.mention}！",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="打工", description="每日打工賺好感度經驗值，附上一張薪資單，運氣好還會遇到特殊事件")
    async def work_command(ctx):
        uid = str(ctx.author.id)
        today = _today_str()
        if _get_last_work_date(uid) == today:
            await ctx.send("💤 今天已經打工過囉，明天再來吧！")
            return

        job = random.choice(WORK_JOBS)
        base_exp = random.randint(*job['exp_range'])

        event = None
        if random.random() < WORK_EVENT_CHANCE:
            event = random.choices(WORK_EVENTS, weights=[e['weight'] for e in WORK_EVENTS], k=1)[0]

        # 只有真的成功套用效果的事件才算數，applied_event 保持 None 就是「這次
        # 事件沒發生」（例如 bonus_image 剛好無圖可送），不會誤顯示事件文字。
        applied_event = None
        bonus_delta = 0
        bonus_image_url = None
        image_saved_to_collection = False

        if event and event['type'] == 'bonus_exp':
            bonus_delta = random.randint(*event['exp_range'])
            applied_event = event
        elif event and event['type'] == 'penalty':
            bonus_delta = -random.randint(*event['exp_range'])
            applied_event = event
        elif event and event['type'] == 'bonus_image':
            collection = get_user_collection(uid)
            curated_pool = [u for u in (BEAUTY_IMAGES + get_custom_images()) if u not in collection]
            if curated_pool:
                bonus_image_url = random.choice(curated_pool)
                collection.append(bonus_image_url)
                save_user_collection(uid, collection)
                image_saved_to_collection = True
                applied_event = event
            else:
                fallback_url = fetch_random_anime_image()
                if fallback_url:
                    bonus_image_url = fallback_url
                    applied_event = event

        # 扣薪事件只會壓低今天賺到的量，不會讓總經驗值倒扣（不然會覺得白打工一場，
        # 娛樂向的 bot 沒必要做到這麼寫實）
        total_exp = max(0, base_exp + bonus_delta)
        _save_work_date(uid, today)
        _add_exp(uid, total_exp)

        description = f"{job['emoji']} **{job['name']}**\n{random.choice(job['messages'])}"
        if applied_event:
            description += f"\n\n{applied_event['label_zh']}：{applied_event['flavor']}"

        embed = discord.Embed(title="💼 打工完成！", description=description, color=discord.Color.from_str("#39C5BB"))

        bonus_label_en = applied_event['label_en'] if applied_event and applied_event['type'] in ('bonus_exp', 'penalty') else None
        payslip_buf = render_payslip(job['label'], today, base_exp, bonus_label_en, bonus_delta, total_exp)
        payslip_file = discord.File(payslip_buf, filename="payslip.png")
        embed.set_image(url="attachment://payslip.png")

        embeds = [embed]
        if bonus_image_url:
            gift_title = "🎁 驚喜禮物到手！已放進珍藏庫" if image_saved_to_collection else "🎁 驚喜禮物到手！"
            gift_embed = discord.Embed(title=gift_title, color=discord.Color.from_str("#C084FC"))
            gift_embed.set_image(url=bonus_image_url)
            embeds.append(gift_embed)

        await ctx.send(embeds=embeds, file=payslip_file)

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

    @bot.hybrid_command(name="移除", description="（僅限主人）從精選圖庫移除一張圖片網址")
    @app_commands.describe(url="要移除的圖片網址（貼跟 /加圖 時一樣的網址）")
    async def remove_image_command(ctx, url: str):
        owner_id = os.getenv("MIKU_OWNER_ID")
        if not owner_id or str(ctx.author.id) != owner_id:
            await ctx.send("❌ 只有小天地主人才能移除精選圖庫喔！")
            return

        if not firebase_admin._apps:
            await ctx.send("❌ Firebase 尚未設定好，暫時無法移除圖庫（不影響現有的 /抽卡）。")
            return

        custom_images = get_custom_images()
        if url not in custom_images:
            if url in BEAUTY_IMAGES:
                await ctx.send("⚠️ 這張圖是寫死在程式碼裡的原始精選圖，沒辦法用這個指令移除，要移除的話要直接改 googleSearch.py 並重新部署。")
            else:
                await ctx.send("⚠️ 找不到這個網址，可能已經不在精選圖庫裡了。")
            return

        custom_images.remove(url)
        save_custom_images(custom_images)
        total = len(BEAUTY_IMAGES) + len(custom_images)
        await ctx.send(f"🗑️ 已從精選圖庫移除這張圖！（目前精選圖庫共 {total} 張）")

    @bot.hybrid_command(name="簽到", description="每日簽到，連續簽到經驗值獎勵會越來越多，還會附上一張簽到行事曆")
    async def checkin_command(ctx):
        uid = str(ctx.author.id)
        now = datetime.now(timezone.utc)
        today = _today_str()
        data = _get_checkin_data(uid) or {}
        last_date = data.get('date')
        prev_streak = data.get('streak', 0)

        if last_date == today:
            embed = discord.Embed(
                title="📅 今天已經簽到過囉！",
                description=f"目前連續簽到 **{prev_streak}** 天，明天再來吧～",
                color=discord.Color.from_str("#39C5BB")
            )
        else:
            streak = prev_streak + 1 if last_date == _yesterday_str() else 1
            exp_gained = CHECKIN_BASE_EXP + min(streak, CHECKIN_STREAK_EXP_CAP)
            _save_checkin(uid, today, streak)
            _add_exp(uid, exp_gained)

            embed = discord.Embed(
                title="✅ 簽到成功！",
                description=f"連續簽到 **{streak}** 天　獲得 **{exp_gained}** 點好感度經驗值",
                color=discord.Color.from_str("#39C5BB")
            )
            if streak > 1 and streak % CHECKIN_MILESTONE_DAYS == 0:
                embed.add_field(
                    name="🎉 連續里程碑！",
                    value=f"已經連續 {streak} 天了，Miku 好感動！繼續保持下去唷～",
                    inline=False
                )

        # 畫這個月的簽到行事曆，已簽到的日期會蓋上 Miku 印章
        checked_dates = _get_checked_dates(uid)
        calendar_buf = render_checkin_calendar(now.year, now.month, checked_dates, today)
        calendar_file = discord.File(calendar_buf, filename="checkin_calendar.png")
        embed.set_image(url="attachment://checkin_calendar.png")
        await ctx.send(embed=embed, file=calendar_file)

    @bot.hybrid_command(name="好感度", description="查看你跟 Miku 的羈絆等級與解鎖進度")
    async def affinity_command(ctx):
        uid = str(ctx.author.id)
        exp = _get_exp(uid)
        level = _level_from_exp(exp)
        exp_into_level = exp % EXP_PER_LEVEL
        exp_to_next = EXP_PER_LEVEL - exp_into_level

        bar_filled = exp_into_level * 10 // EXP_PER_LEVEL
        bar = "🟩" * bar_filled + "⬜" * (10 - bar_filled)

        embed = discord.Embed(
            title=f"💚 與 Miku 的羈絆　Lv.{level}",
            description=f"{bar}\n{exp_into_level}/{EXP_PER_LEVEL} exp（還差 {exp_to_next} 點升級）",
            color=discord.Color.from_str("#39C5BB")
        )
        unlock_text = "\n".join(
            f"{'✅' if level >= lv else '🔒'} Lv.{lv}　{name}" for lv, name in AFFINITY_UNLOCKS
        )
        embed.add_field(name="解鎖進度", value=unlock_text, inline=False)
        if level >= 39:
            embed.add_field(
                name="🌟 39 稱號：唯一的觀眾",
                value="不管唱多少遍，你永遠都在最前排守候——謝謝你，39 (Thank you) ♪",
                inline=False
            )
        embed.set_footer(text="💡 使用 /運勢、/抽卡 都可以累積好感度經驗值")
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="選單", aliases=["help", "指令"], description="顯示 MIKU39 的指令說明")
    async def menu_command(ctx):
        embed = discord.Embed(
            title="🎤 MIKU39 指令選單",
            description="以下是目前可以使用的指令：\n──────────────────",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.add_field(name="`/運勢`", value="抽一次今日運勢籤詩，每天限抽一次（如果你已經在 Osu Bot 用過 `/link` 綁定帳號，運勢會偷偷參考你最近的 osu! 排名升降喔）", inline=False)
        embed.add_field(name="`/抽卡`", value=f"隨機抽一張美圖，分 ⚪N／🔵R／🟣SR 三種稀有度，可以收藏到珍藏庫。每日限抽 {GACHA_DAILY_LIMIT} 次，連續 {GACHA_PITY_THRESHOLD} 次沒中 R 以上會自動保底！", inline=False)
        embed.add_field(name="`/珍藏庫`", value="翻看你收藏的美圖，可以上一張／下一張／移除", inline=False)
        embed.add_field(name="`/贈送 @對象 [網址]`", value="把珍藏庫裡的一張圖送給其他人", inline=False)
        embed.add_field(name="`/簽到`", value="每日簽到，連續簽到經驗值獎勵會越來越多，中斷一天就重新從第 1 天算起", inline=False)
        embed.add_field(name="`/打工`", value="每日打工賺好感度經驗值，隨機分配工作並附上薪資單，機率觸發加班費／驚喜禮物／扣薪等特殊事件", inline=False)
        embed.add_field(name="`/好感度`", value="查看你跟 Miku 的羈絆等級，`/運勢`、`/抽卡`、`/簽到`、`/打工` 都會累積經驗值，升級解鎖隱藏籤詩、保底門檻降低等內容", inline=False)
        owner_id = os.getenv("MIKU_OWNER_ID")
        if owner_id and str(ctx.author.id) == owner_id:
            embed.add_field(name="`/加圖 [網址]`", value="（僅限主人）把新的圖片網址加進精選圖庫，立即生效不用重新部署", inline=False)
            embed.add_field(name="`/移除 [網址]`", value="（僅限主人）從精選圖庫移除一張圖片網址", inline=False)
        embed.set_footer(text="💚 想再看一次這份選單，隨時輸入 /選單 或 bot 選單")
        await ctx.send(embed=embed)