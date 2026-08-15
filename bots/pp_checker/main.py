import os
import urllib.request
import random
import json
import glob as glob_mod
import requests
import discord
from discord.ext import commands
from ossapi import Ossapi, Mod
import rosu_pp_py
from flask import Flask, request, jsonify, render_template_string
from threading import Thread

# ============ Flask 伺服器 ============
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/maps')
def maps_page():
    return render_template_string(MAPS_HTML)

# ============ Flask API 路由 ============

@app.route('/api/maps')
def api_maps():
    min_pp = request.args.get('min_pp', 0, type=int)
    max_pp = request.args.get('max_pp', 9999, type=int)
    all_maps = load_all_maps()
    filtered = [m for m in all_maps if min_pp <= m.get('p', 0) <= max_pp]
    filtered.sort(key=lambda m: m.get('p', 0))
    
    # 這裡確保把 JSON 檔案裡的 title, artist, version 完整帶給前端網頁
    results = []
    for m in filtered[:100]:  # 最多顯示前 100 筆
        results.append({
            "b": m.get("b"), 
            "s": m.get("s", 0), 
            "p": m.get("p", 0), 
            "m": m.get("m", "NoMod"),
            "title": m.get("title"),
            "artist": m.get("artist"),
            "version": m.get("version")
        })
    return jsonify(results)


# ============ 網頁 HTML 模板 ============
MAPS_HTML = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PP Farm 圖庫搜尋</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #eee; font-family: 'Segoe UI', sans-serif; padding: 20px; }
  h1 { text-align: center; color: #ff66aa; margin-bottom: 20px; }
  .search-box { display: flex; justify-content: center; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
  .search-box input { padding: 10px 15px; border: 2px solid #ff66aa; border-radius: 8px;
    background: #16213e; color: #eee; font-size: 16px; width: 150px; text-align: center; }
  .search-box button { padding: 10px 25px; border: none; border-radius: 8px;
    background: #ff66aa; color: #fff; font-size: 16px; cursor: pointer; font-weight: bold; }
  .search-box button:hover { background: #ff8ec4; }
  table { width: 100%; border-collapse: collapse; max-width: 900px; margin: 0 auto; }
  th { background: #16213e; color: #ff66aa; padding: 12px; text-align: left; border-bottom: 2px solid #ff66aa; }
  td { padding: 10px 12px; border-bottom: 1px solid #333; vertical-align: middle; }
  tr:hover { background: #16213e; }
  .cover { width: 80px; height: 45px; object-fit: cover; border-radius: 4px; }
  .song-link { color: #ff66aa; text-decoration: none; font-weight: bold; }
  .song-link:hover { text-decoration: underline; }
  .mod-badge { background: #ff66aa; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 13px; }
  .pp-val { color: #ffd700; font-weight: bold; }
  .info { text-align: center; color: #888; margin-top: 15px; }
  .loading { text-align: center; color: #ff66aa; display: none; margin: 20px; }
</style>
</head>
<body>
<h1>PP Farm 圖庫搜尋</h1>
<div class="search-box">
  <input type="number" id="minPP" placeholder="最小 PP" value="200">
  <input type="number" id="maxPP" placeholder="最大 PP" value="300">
  <button onclick="searchMaps()">搜尋</button>
</div>
<div class="loading" id="loading">搜尋中...</div>
<div class="info" id="info"></div>
<table>
  <thead>
    <tr><th>封面</th><th>地圖連結 (歌名)</th><th>PP</th><th>Mod</th></tr>
  </thead>
  <tbody id="results"></tbody>
</table>

<script>
function searchMaps() {
  const min = document.getElementById('minPP').value || 0;
  const max = document.getElementById('maxPP').value || 9999;
  const tbody = document.getElementById('results');
  const loading = document.getElementById('loading');
  const info = document.getElementById('info');
  tbody.innerHTML = '';
  info.textContent = '';
  loading.style.display = 'block';
  
  fetch(`/api/maps?min_pp=${min}&max_pp=${max}`)
    .then(r => r.json())
    .then(data => {
      loading.style.display = 'none';
      info.textContent = `找到 ${data.length} 張地圖 (最多顯示前 100 筆)`;
      
      data.forEach(m => {
        const coverUrl = m.s ? `https://assets.ppy.sh/beatmaps/${m.s}/covers/cover.jpg` : '';
        const href = `https://osu.ppy.sh/b/${m.b}`;
        
        // 核心邏輯：如果 JSON 檔裡有完整的 title 就拿來做為超連結文字！
        let displayName = `前往地圖頁面 (ID: ${m.b})`;
        if (m.title) {
          const artist = m.artist ? `${m.artist} - ` : '';
          const version = m.version ? ` [${m.version}]` : '';
          displayName = `${artist}${m.title}${version}`;
        }
        
        tbody.innerHTML += `<tr>
          <td>${coverUrl ? `<img class="cover" src="${coverUrl}" onerror="this.style.display='none'">` : '無封面'}</td>
          <td><a class="song-link" href="${href}" target="_blank">${displayName}</a></td>
          <td class="pp-val">${m.p} pp</td>
          <td><span class="mod-badge">${m.m}</span></td>
        </tr>`;
      });
    });
}
searchMaps();
</script>
</body>
</html>
"""

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
def load_all_maps():
    all_maps = []
    seen = set()
    for path in sorted(glob_mod.glob("maps_*.json")):
        with open(path, "r", encoding="utf-8") as f:
            for m in json.load(f):
                b = m.get("b")
                if b not in seen:
                    seen.add(b)
                    all_maps.append(m)
    return all_maps

# osu-花火網頁 的農圖庫 API：由該網站的 farm-crawl-cron 每 10 分鐘自動爬蟲更新，
# 資料本身已經內含 title/artist/version，!rec 不用再自己額外查一次 beatmap 資訊
FARM_MAPS_API = "https://osu-collection-hanabi.netlify.app/.netlify/functions/farm-maps-list"

def fetch_farm_maps(pp_min=None, pp_max=None, mods="NM", mode="osu"):
    params = {"mode": mode, "mods": mods, "page": 0}
    if pp_min is not None:
        params["ppMin"] = pp_min
    if pp_max is not None:
        params["ppMax"] = pp_max
    resp = requests.get(FARM_MAPS_API, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])

# ============ Discord Bot 指令 ============
@bot.event
async def on_ready():
    print(f"PP查詢員已上線：{bot.user}")

# 指令用法錯誤（缺參數/參數型別錯）預設只會印到 log、使用者完全看不到任何回覆，
# 補上一個全域錯誤處理，讓打錯指令的人至少會收到用法提示
COMMAND_USAGE = {
    'acc': "用法：`!acc [beatmap_id] [accuracy] [mods]`，例如 `!acc 1234567 98.5 HD`",
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

@bot.command()
async def ping(ctx):
    await ctx.send("pong! 🏓")

# --- 1. 預估 PP 查詢指令 (!acc) ---
@bot.command()
async def acc(ctx, beatmap_id: int, accuracy: float, mods_str: str = ""):
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
        calculator = rosu_pp_py.Performance(accuracy=accuracy, mods=mods_value)
        result = calculator.calculate(parsed_map)

        embed = discord.Embed(
            title=f"{beatmap.beatmapset().artist} - {beatmap.beatmapset().title}",
            url=f"https://osu.ppy.sh/b/{beatmap_id}",
            color=discord.Color.from_rgb(255, 102, 170)
        )
        embed.add_field(name="難度名稱", value=beatmap.version, inline=False)
        embed.add_field(name="指定 Mod", value=mods_str.upper() if mods_str else "No Mod", inline=True)
        embed.add_field(name="指定 Accuracy", value=f"{accuracy}%", inline=True)
        embed.add_field(name="預估 PP", value=f"**{result.pp:.2f} pp**", inline=False)
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

@bot.command()
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

        await ctx.send(f"🔍 正在從網站農圖庫搜尋 {min_pp}~{max_pp}pp（{mods}）的地圖...")

        try:
            suitable = fetch_farm_maps(pp_min=min_pp, pp_max=max_pp, mods=mods)
        except Exception as e:
            print(f"farm-maps-list 查詢失敗: {e}")
            return await ctx.send("❌ 連線農圖庫網站失敗，請稍後再試。")

        if not suitable:
            return await ctx.send(f"😢 找不到 {min_pp}~{max_pp}pp（{mods}）範圍內的地圖。")

        # 先徹底打亂符合條件的清單，再抽取前 10 張，保證每次都隨機
        random.shuffle(suitable)
        shown = suitable[:10]

        # 用 Thumbnail（不是 set_image）避免被 Discord 合併圖片
        embeds = []

        for index, m in enumerate(shown):
            b_id = m.get('beatmap_id')
            s_id = m.get('beatmapset_id')
            pp = m.get('pp', 0)
            name = f"{m.get('artist')} - {m.get('title')} [{m.get('version')}]"

            emb = discord.Embed(
                title=f"#{index + 1} | {pp:.0f}pp | Mod: {mods}",
                description=f"🎵 **[{name}](https://osu.ppy.sh/b/{b_id})**",
                color=discord.Color.from_rgb(255, 102, 170)
            )

            if s_id:
                emb.set_thumbnail(url=f"https://assets.ppy.sh/beatmaps/{s_id}/covers/list.jpg")

            if index == len(shown) - 1:
                emb.set_footer(text=f"共找到 {len(suitable)} 張，隨機顯示其中 {len(shown)} 張 | 資料來源：osu-花火網頁 農圖庫")

            embeds.append(emb)

        await ctx.send(embeds=embeds)
        return

    # --- 單一目標 PP：隨機抽一張 ---
    try:
        target_pp_int = int(target_pp)
    except ValueError:
        return await ctx.send("❌ 請輸入數字，例如 `!rec 400` 或 `!rec 200-300`")

    await ctx.send(f"🔍 正在從網站農圖庫搜尋 {target_pp_int}pp（{mods}）左右的推薦地圖...")

    try:
        suitable_maps = fetch_farm_maps(pp_min=target_pp_int - 10, pp_max=target_pp_int + 10, mods=mods)

        if not suitable_maps:
            level = (target_pp_int // 100) * 100
            suitable_maps = fetch_farm_maps(pp_min=level, pp_max=level + 99, mods=mods)
            if suitable_maps:
                await ctx.send(f"⚠️ 提示：沒有剛好在 {target_pp_int}±10pp 內的地圖，改從整個 {level}pp 範圍中隨機抽選。")

        if not suitable_maps:
            suitable_maps = fetch_farm_maps(pp_min=target_pp_int - 50, pp_max=target_pp_int + 50, mods=mods)
            if suitable_maps:
                await ctx.send(f"⚠️ 提示：找不到 {target_pp_int}pp 附近的地圖，改從 ±50pp 範圍中隨機抽選。")
    except Exception as e:
        print(f"farm-maps-list 查詢失敗: {e}")
        return await ctx.send("❌ 連線農圖庫網站失敗，請稍後再試。")

    if not suitable_maps:
        return await ctx.send(f"😢 網站農圖庫目前還沒有 {target_pp_int}pp（{mods}）附近的地圖資料。")

    chosen_map = random.choice(suitable_maps)
    b_id = chosen_map.get('beatmap_id')
    s_id = chosen_map.get('beatmapset_id')
    avg_pp = chosen_map.get('pp', 0)
    name = f"{chosen_map.get('artist')} - {chosen_map.get('title')} [{chosen_map.get('version')}]"

    embed = discord.Embed(
        title=f"✨ 幫你找到一張 {avg_pp:.0f}pp 左右的農圖囉！",
        description=f"🎵 **[{name}](https://osu.ppy.sh/b/{b_id})**",
        color=discord.Color.from_rgb(255, 102, 170)
    )
    embed.add_field(name="地圖 ID (Beatmap ID)", value=f"`{b_id}`", inline=True)
    embed.add_field(name="推薦搭配 Mod", value=f"`{mods}`", inline=True)
    embed.add_field(name="預估 PP", value=f"`{avg_pp:.0f} pp`", inline=True)

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