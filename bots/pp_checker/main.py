import os
import urllib.request
import random
import requests
import discord
from discord import app_commands
from discord.ext import commands
from ossapi import Ossapi, Mod
import rosu_pp_py
from flask import Flask
from threading import Thread

# Slash 指令同步到這個伺服器（幾乎立即生效，不用等 Discord 全域同步最長 1 小時的傳播時間）
GUILD = discord.Object(id=1505477519753609226)

# ============ Flask 伺服器（防斷線健康檢查用，內容見檔案底部 keep_alive）============
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

# ============ 環境變數 ============
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    raise RuntimeError("請設定 DISCORD_TOKEN 環境變數")
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")
if not OSU_CLIENT_ID or not OSU_CLIENT_SECRET:
    raise RuntimeError("請設定 OSU_CLIENT_ID 與 OSU_CLIENT_SECRET 環境變數")
OSU_CLIENT_ID = int(OSU_CLIENT_ID)

# ============ 初始化 ============
osu_api = Ossapi(OSU_CLIENT_ID, OSU_CLIENT_SECRET)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

if not os.path.exists("maps"):
    os.makedirs("maps")

# ============ 工具函式 ============
# osu-花火網頁 的農圖庫 API：由該網站的 farm-crawl-cron 每 10 分鐘自動爬蟲更新，
# 資料本身已經內含 title/artist/version，!rec 不用再自己額外查一次 beatmap 資訊
FARM_MAPS_API = "https://osu-collection-hanabi.netlify.app/.netlify/functions/farm-maps-list"

def fetch_farm_maps(pp_min=None, pp_max=None, mods="NM", mode="osu", farm_only=False):
    params = {"mode": mode, "mods": mods, "page": 0}
    if pp_min is not None:
        params["ppMin"] = pp_min
    if pp_max is not None:
        params["ppMax"] = pp_max
    if farm_only:
        params["farmOnly"] = "1"
    resp = requests.get(FARM_MAPS_API, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])

# ============ Discord Bot 指令 ============
@bot.event
async def setup_hook():
    # 把全域註冊的 hybrid 指令複製到指定伺服器並同步，這樣 /指令 幾乎立即生效，
    # 不用等 Discord 全域同步最長 1 小時的傳播時間
    bot.tree.copy_global_to(guild=GUILD)
    synced = await bot.tree.sync(guild=GUILD)
    print(f"✅ 已同步 {len(synced)} 個 Slash 指令到伺服器")

@bot.event
async def on_ready():
    print(f"PP查詢員已上線：{bot.user}")

# 指令用法錯誤（缺參數/參數型別錯）預設只會印到 log、使用者完全看不到任何回覆，
# 補上一個全域錯誤處理，讓打錯指令的人至少會收到用法提示
COMMAND_USAGE = {
    'acc': "用法：`!acc [beatmap_id] [accuracy] [Mod] [combo] [miss數]`，例如 `!acc 1234567 98.5 HD` 或 `!acc 1234567 98.5 HDDT 520 2`（Mod/combo/miss 皆可省略）",
    'rec': "用法：`!rec [目標PP] [Mod]` 或 `!rec [最小PP-最大PP] [Mod]`，例如 `!rec 400`、`!rec 400 DT`、`!rec 200-300 HR`（Mod 可省略，預設 NM，支援 NM/DT/HD/HDDT/HR/HDHR）",
}

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        usage = COMMAND_USAGE.get(ctx.command.name if ctx.command else None)
        await ctx.send(f"❌ {usage}" if usage else "❌ 參數格式不正確，請確認輸入的內容。")
        return
    print(f"[pp_checker] 未處理的指令錯誤: {error}")

@bot.hybrid_command(description="測試機器人是否存活")
async def ping(ctx):
    await ctx.send("pong! 🏓")

# --- 1. 預估 PP 查詢指令 (!acc) ---
@bot.hybrid_command(description="計算指定圖／ACC／Mod／combo／miss 組合下的預估 PP")
@app_commands.describe(
    beatmap_id="Beatmap ID（osu! 地圖網址最後那串數字）",
    accuracy="準確度（0~100 的百分比數字）",
    mods_str="Mod 組合，例如 HD、HDDT（可省略，預設 No Mod）",
    combo="最大連段數（可省略，預設當作 Full Combo）",
    misses="Miss 數（可省略，預設 0）",
)
async def acc(ctx, beatmap_id: int, accuracy: float, mods_str: str = "", combo: int = None, misses: int = None):
    """
    用法:
      !acc [beatmap_id] [accuracy] [Mod] [combo] [miss數]
      例如 !acc 1234567 98.5 HD、!acc 1234567 98.5 HDDT 520 2
      combo/miss 可省略（預設當作 Full Combo、0 miss 計算），有帶的話算出來的 PP 會更貼近實際那一次的遊玩
    """
    await ctx.send("⏳ 正在計算中，請稍候...")
    map_path = f"maps/{beatmap_id}.osu"
    if not os.path.exists(map_path):
        try:
            url = f"https://osu.ppy.sh/osu/{beatmap_id}"
            urllib.request.urlretrieve(url, map_path)
        except:
            return await ctx.send(f"❌ 無法下載地圖 ID {beatmap_id}。")

    try:
        beatmap = osu_api.beatmap(beatmap_id)
        mods_value = 0
        if mods_str:
            cleaned_str = mods_str.upper().strip()
            mods_list = [cleaned_str[i:i+2] for i in range(0, len(cleaned_str), 2)]
            for m in mods_list:
                if hasattr(Mod, m):
                    mods_value |= getattr(Mod, m).value
                else:
                    return await ctx.send(f"❌ 找不到 Mod: `{m}`")

        parsed_map = rosu_pp_py.Beatmap(path=map_path)
        diff_attrs = rosu_pp_py.Difficulty(mods=mods_value).calculate(parsed_map)

        perf_kwargs = {"accuracy": accuracy, "mods": mods_value}
        clamped_combo = None
        if combo is not None:
            clamped_combo = min(combo, diff_attrs.max_combo)
            perf_kwargs["combo"] = clamped_combo
        if misses is not None:
            perf_kwargs["misses"] = misses

        result = rosu_pp_py.Performance(**perf_kwargs).calculate(diff_attrs)

        star = diff_attrs.stars
        beatmapset = beatmap.beatmapset()
        mods_display = mods_str.upper() if mods_str else "NM"

        embed = discord.Embed(
            title=f"{beatmapset.artist} - {beatmapset.title}",
            url=f"https://osu.ppy.sh/b/{beatmap_id}",
            description=f"[{beatmap.version}] mapped by {beatmapset.creator}",
            color=star_color(star)
        )
        embed.add_field(name="⭐ 星數", value=f"{star:.2f}★", inline=True)
        embed.add_field(name="🎯 預估 PP", value=f"{result.pp:.2f}pp", inline=True)
        embed.add_field(name="🎮 Mod", value=f"`{mods_display}`", inline=True)
        embed.add_field(name="🥁 BPM", value=f"{beatmap.bpm or 0:.0f}", inline=True)
        embed.add_field(name="⏱️ 長度", value=format_length(beatmap.total_length), inline=True)
        embed.add_field(name="📐 Accuracy", value=f"{accuracy}%", inline=True)
        if clamped_combo is not None:
            embed.add_field(name="🔗 Combo", value=f"{clamped_combo}x / {diff_attrs.max_combo}x", inline=True)
        if misses is not None:
            embed.add_field(name="❌ Miss", value=f"{misses}", inline=True)
        embed.set_footer(text="HANABI PP 計算系統")

        try:
            acc_s_id = beatmap.beatmapset_id
            if acc_s_id:
                embed.set_image(url=f"https://assets.ppy.sh/beatmaps/{acc_s_id}/covers/cover.jpg?v={random.random()}")
        except Exception as img_err:
            print(f"acc 圖片獲取失敗: {img_err}")

        await ctx.send(embed=embed)
    except Exception as e:
        print(e)
        await ctx.send("❌ 計算過程中發生錯誤。")

# --- 2. 分類毒瘤抽圖指令 (!rec) ---
# 資料來源改成 osu-花火網頁 的農圖庫 API（自動爬蟲更新），不再讀本地 maps_*.json
FARM_MODS = {"NM", "DT", "HD", "HDDT", "HR", "HDHR"}
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

def star_color(star):
    """依星數給對應顏色，跟 osu! 官方難度色系一致（農圖庫本身星數下限 5.5，
    所以這裡的分段是針對「高難度」區間微調過的，橘→粉→紫→深紫，難度越高顏色越深）"""
    star = star or 0
    if star < 6.5:
        return discord.Color.from_rgb(255, 165, 60)
    if star < 7.5:
        return discord.Color.from_rgb(255, 102, 170)
    if star < 9.0:
        return discord.Color.from_rgb(180, 90, 255)
    if star < 11.0:
        return discord.Color.from_rgb(120, 60, 220)
    return discord.Color.from_rgb(60, 30, 80)

def format_length(seconds):
    seconds = int(seconds or 0)
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"

@bot.hybrid_command(description="從農圖庫推薦圖：單一目標 PP 隨機抽一張，或用 最小-最大 列出範圍內的圖")
@app_commands.describe(
    target_pp="目標 PP（例如 400）或 PP 範圍（例如 200-300）",
    mods="Mod 組合：NM/DT/HD/HDDT/HR/HDHR（可省略，預設 NM）",
)
async def rec(ctx, target_pp: str, mods: str = "NM"):
    """
    用法:
      !rec 400           → 隨機抽一張 NM ~400pp 的圖
      !rec 400 DT        → 指定 Mod（NM/DT/HD/HDDT/HR/HDHR）
      !rec 200-300       → 列出 200~300pp 的所有圖（最多 10 張，每張皆含橫幅）
      !rec 200-300 HR    → 範圍搜尋一樣可以指定 Mod
    """
    mods = mods.upper()
    if mods not in FARM_MODS:
        return await ctx.send(f"❌ 不支援的 Mod：`{mods}`，目前支援 {', '.join(sorted(FARM_MODS))}")

    # --- 範圍搜尋 ---
    if "-" in target_pp:
        try:
            parts = target_pp.split("-")
            min_pp, max_pp = int(parts[0]), int(parts[1])
        except ValueError:
            return await ctx.send("❌ 格式錯誤，請用 `!rec 最小PP-最大PP`，例如 `!rec 200-300`")

        await ctx.send(f"🔍 正在從網站農圖庫搜尋 {min_pp}~{max_pp}pp（{mods}）的農圖...")

        try:
            suitable = fetch_farm_maps(pp_min=min_pp, pp_max=max_pp, mods=mods, farm_only=True)
            if not suitable:
                suitable = fetch_farm_maps(pp_min=min_pp, pp_max=max_pp, mods=mods)
                if suitable:
                    await ctx.send("⚠️ 提示：這個範圍內符合農圖標準的圖還沒被爬蟲分類完（資料庫持續擴充中），先顯示範圍內的所有圖。")
        except Exception as e:
            print(f"farm-maps-list 查詢失敗: {e}")
            return await ctx.send("❌ 連線農圖庫網站失敗，請稍後再試。")

        if not suitable:
            return await ctx.send(f"😢 找不到 {min_pp}~{max_pp}pp（{mods}）範圍內的地圖。")

        # 先徹底打亂符合條件的清單，再抽取前 10 張，保證每次都隨機
        random.shuffle(suitable)
        shown = suitable[:10]

        embeds = []

        for index, m in enumerate(shown):
            b_id = m.get('beatmap_id')
            s_id = m.get('beatmapset_id')
            pp = m.get('pp', 0)
            star = m.get('star', 0)
            bpm = m.get('bpm', 0)
            name = f"{m.get('artist')} - {m.get('title')}"
            num = NUMBER_EMOJIS[index] if index < len(NUMBER_EMOJIS) else f"#{index + 1}"

            emb = discord.Embed(
                title=f"{num} {name}",
                url=f"https://osu.ppy.sh/b/{b_id}",
                description=f"[{m.get('version')}]",
                color=star_color(star)
            )
            emb.add_field(name="PP", value=f"{pp:.0f}pp", inline=True)
            emb.add_field(name="★", value=f"{star:.2f}", inline=True)
            emb.add_field(name="BPM", value=f"{bpm:.0f}", inline=True)

            if s_id:
                emb.set_image(url=f"https://assets.ppy.sh/beatmaps/{s_id}/covers/cover.jpg?v={random.random()}")

            if index == len(shown) - 1:
                emb.set_footer(text=f"共找到 {len(suitable)} 張，隨機顯示其中 {len(shown)} 張 | Mod: {mods} | 資料來源：osu-花火網頁 農圖庫")

            embeds.append(emb)

        await ctx.send(embeds=embeds)
        return

    # --- 單一目標 PP：隨機抽一張 ---
    try:
        target_pp_int = int(target_pp)
    except ValueError:
        return await ctx.send("❌ 請輸入數字，例如 `!rec 400` 或 `!rec 200-300`")

    await ctx.send(f"🔍 正在從網站農圖庫搜尋 {target_pp_int}pp（{mods}）左右的農圖...")

    try:
        suitable_maps = fetch_farm_maps(pp_min=target_pp_int - 10, pp_max=target_pp_int + 10, mods=mods, farm_only=True)

        if not suitable_maps:
            level = (target_pp_int // 100) * 100
            suitable_maps = fetch_farm_maps(pp_min=level, pp_max=level + 99, mods=mods, farm_only=True)
            if suitable_maps:
                await ctx.send(f"⚠️ 提示：沒有剛好在 {target_pp_int}±10pp 內的農圖，改從整個 {level}pp 範圍中隨機抽選。")

        if not suitable_maps:
            suitable_maps = fetch_farm_maps(pp_min=target_pp_int - 50, pp_max=target_pp_int + 50, mods=mods, farm_only=True)
            if suitable_maps:
                await ctx.send(f"⚠️ 提示：找不到 {target_pp_int}pp 附近的農圖，改從 ±50pp 範圍中隨機抽選。")

        # 農圖分類還在backfill中：整條 farm_only 鏈都落空時，退回不限定農圖標準的原始查詢
        if not suitable_maps:
            suitable_maps = fetch_farm_maps(pp_min=target_pp_int - 10, pp_max=target_pp_int + 10, mods=mods)
            if suitable_maps:
                await ctx.send("⚠️ 提示：這個 PP 範圍符合農圖標準的圖還沒被爬蟲分類完（資料庫持續擴充中），先顯示範圍內的所有圖。")
    except Exception as e:
        print(f"farm-maps-list 查詢失敗: {e}")
        return await ctx.send("❌ 連線農圖庫網站失敗，請稍後再試。")

    if not suitable_maps:
        return await ctx.send(f"😢 網站農圖庫目前還沒有 {target_pp_int}pp（{mods}）附近的地圖資料。")

    chosen_map = random.choice(suitable_maps)
    b_id = chosen_map.get('beatmap_id')
    s_id = chosen_map.get('beatmapset_id')
    avg_pp = chosen_map.get('pp', 0)
    star = chosen_map.get('star', 0)
    bpm = chosen_map.get('bpm', 0)
    length = format_length(chosen_map.get('total_length'))
    version = chosen_map.get('version', '')
    creator = chosen_map.get('creator') or '？'
    name = f"{chosen_map.get('artist')} - {chosen_map.get('title')}"

    embed = discord.Embed(
        title=f"✨ {name}",
        url=f"https://osu.ppy.sh/b/{b_id}",
        description=f"[{version}] mapped by {creator}",
        color=star_color(star)
    )
    embed.add_field(name="⭐ 星數", value=f"{star:.2f}★", inline=True)
    embed.add_field(name="🎯 預估 PP", value=f"{avg_pp:.0f}pp", inline=True)
    embed.add_field(name="🎮 Mod", value=f"`{mods}`", inline=True)
    embed.add_field(name="🥁 BPM", value=f"{bpm:.0f}", inline=True)
    embed.add_field(name="⏱️ 長度", value=length, inline=True)
    embed.add_field(name="🆔 Beatmap ID", value=f"`{b_id}`", inline=True)

    if s_id:
        banner_url = f"https://assets.ppy.sh/beatmaps/{s_id}/covers/cover.jpg?v={random.random()}"
        embed.set_image(url=banner_url)
    embed.set_footer(text="資料來源：osu-花火網頁 農圖庫（每 10 分鐘自動更新）")

    await ctx.send(embed=embed)

# ====================================================
#  補回消失的 keep_alive 區塊 (請加在 bot.run 的上方)
# ====================================================
def run():
    # 這裡的 port 依照你原來的設定，設定為 10000 讓 Render 讀取
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

# ============ 啟動 ============
# 由 supervisor.py 統一啟動時（SUPERVISED=1），健康檢查改由 supervisor 負責，
# 避免三隻 bot 各自搶同一個 port 10000
if not os.getenv("SUPERVISED"):
    keep_alive()
bot.run(DISCORD_TOKEN)