import os
import requests
import discord
from discord import app_commands
from discord.ext import commands
from firebase_admin import db
from ossapi import Ossapi

# ========================================================
# 機器人核心設定與常數
# ========================================================
OSU_CLIENT_ID = os.getenv("OSU_CLIENT_ID")
OSU_CLIENT_SECRET = os.getenv("OSU_CLIENT_SECRET")
if not OSU_CLIENT_ID or not OSU_CLIENT_SECRET:
    raise RuntimeError("請設定 OSU_CLIENT_ID 與 OSU_CLIENT_SECRET 環境變數")

# osu! API v2（client credentials，跟 pp_checker 共用同一組 OAuth App 也沒問題）
osu_api = Ossapi(int(OSU_CLIENT_ID), OSU_CLIENT_SECRET)

# osu-花火網頁的圖庫收藏清單（公開、免驗證），用來查詢綁定成員在網站上發布的收藏摘要
COLLECTIONS_API = "https://osu-collection-hanabi.netlify.app/.netlify/functions/collections-list"

def fetch_collection_summary(osu_username):
    """依 osu! 使用者名稱查詢該玩家在網站上發布的收藏摘要，查不到回傳 None"""
    resp = requests.get(COLLECTIONS_API, params={"q": osu_username, "page": 0}, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    lname = osu_username.lower()
    for item in items:
        if (item.get("username") or "").lower() == lname:
            return item
    return None

# 🎯 mode_id -> (v2 API 的 ruleset 名稱, 顯示用文字)
OSU_MODES = {
    0: ("osu", "⭕ osu! Standard (標準模式)"),
    1: ("taiko", "🥁 osu! Taiko (太鼓模式)"),
    2: ("fruits", "🍎 osu! Catch (接水果模式)"),
    3: ("mania", "🎹 osu! Mania (狂熱模式)")
}

RANK_ANSI_STRINGS = {
    "X": "[1;33mSS[0m",     # 金色 SS
    "XH": "[1;36mSS[0m",    # Iron SS (白銀色)
    "S": "[1;33mS[0m",      # 金色 S
    "SH": "[1;36mS[0m",     # Iron S (白銀色)
    "A": "[1;32mA[0m",      # 綠色 A
    "B": "[1;34mB[0m",      # 藍色 B
    "C": "[1;33mC[0m",      # 黃色 C
    "D": "[1;31mD[0m"       # 紅色 D
}

# ========================================================
# 🛠️ 核心工具函式
# ========================================================
def parse_mods(mods):
    """把 v2 API 回傳的 mods 物件列表轉成字串（例如：HDDT）"""
    if not mods:
        return "NM"
    return "".join(m.acronym for m in mods) or "NM"


def error_embed(text):
    """統一的錯誤訊息樣式，取代原本散落各處的純文字 ❌ 訊息"""
    return discord.Embed(description=f"❌ {text}", color=discord.Color.red())


def info_embed(text):
    """統一的提示訊息樣式（不算錯誤，只是引導性質，例如「還沒有資料」）"""
    return discord.Embed(description=text, color=discord.Color.from_rgb(255, 102, 170))


def resolve_user_id(osu_name, osu_user_id):
    """user_scores() 只能吃數字 user_id，這裡確保一定有一個可用的 id"""
    if osu_user_id:
        return osu_user_id
    user = osu_api.user(osu_name, key="username")
    return user.id


def generate_mode_embed(osu_name, osu_user_id, mode_id, author_mention, author_avatar_url):
    """抓取特定模式的 Top 5 並生成對應 Embed"""
    mode_key, mode_name = OSU_MODES[mode_id]

    embed = discord.Embed(
        title=f"🏆 {osu_name} 的 {mode_name} Top 1-5 表現",
        color=discord.Color.from_rgb(255, 102, 170)
    )

    osu_profile_link = f"https://osu.ppy.sh/users/{osu_user_id if osu_user_id else osu_name}"
    embed.description = (
        f"✨ **伺服器成員**：{osu_name}\n"
        f"• **Discord 帳號**：{author_mention}\n"
        f"• **osu! 個人檔案**：[點擊前往個人主頁]({osu_profile_link})\n"
        f"──────────────────"
    )

    if osu_user_id:
        embed.set_thumbnail(url=f"https://a.ppy.sh/{osu_user_id}")
    else:
        embed.set_thumbnail(url=author_avatar_url)

    try:
        user_id = resolve_user_id(osu_name, osu_user_id)
        best_plays = osu_api.user_scores(user_id, type="best", mode=mode_key, limit=5)

        if not best_plays:
            embed.add_field(name="提示", value="```ansi\n[1;30m* 目前沒有此模式的遊玩紀錄 *[0m\n```", inline=False)
            return embed

        for index, play in enumerate(best_plays):
            beatmap = play.beatmap
            beatmapset = play.beatmapset
            beatmap_id = beatmap.id if beatmap else play.beatmap_id

            pp = play.pp or 0.0
            acc = (play.accuracy or 0.0) * 100
            mods_text = parse_mods(play.mods)
            colored_rank = RANK_ANSI_STRINGS.get(play.rank.value, play.rank.value)

            map_title = beatmapset.title if beatmapset else "未知譜面歌曲"
            map_version = beatmap.version if beatmap else "未知難度"

            clean_title = map_title.replace('[', '［').replace(']', '］')
            clean_version = map_version.replace('[', '［').replace(']', '］')
            download_link = f"https://osu.ppy.sh/b/{beatmap_id}"

            field_value = f"🎵 {clean_title} ［{clean_version}］\n"
            field_value += f"🔗 譜面連結: <{download_link}>\n"

            field_value += "```ansi\n"
            field_value += f"🎖️ [1;30m資訊[0m | 譜面ID: [1;30m{beatmap_id:<8}[0m | [1;35m{pp:>6.2f} PP[0m | [1;36m{acc:>6.2f}%[0m | {colored_rank} [1;37m({mods_text})[0m```"

            embed.add_field(
                name=f"#{index+1} 最佳表現",
                value=field_value,
                inline=False
            )
    except Exception as e:
        print(f"generate_mode_embed 失敗: {e}")
        embed.add_field(name="錯誤", value="```ansi\n[1;31m❌ 連線官方 API 失敗[0m\n```", inline=False)

    return embed


# ========================================================
# 🔘 模式切換按鈕 View 元件（本人專屬 + 永不過期版）
# ========================================================
class OsuModeView(discord.ui.View):
    def __init__(self, ctx, osu_name, osu_user_id):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.osu_name = osu_name
        self.osu_user_id = osu_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ 這不是你的對話面板，請自己輸入 `!top` 查詢喔！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Standard", style=discord.ButtonStyle.primary, emoji="⭕", custom_id="osu_btn_std")
    async def std_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_mode_embed(self.osu_name, self.osu_user_id, 0, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Taiko", style=discord.ButtonStyle.success, emoji="🥁", custom_id="osu_btn_taiko")
    async def taiko_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_mode_embed(self.osu_name, self.osu_user_id, 1, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Catch", style=discord.ButtonStyle.danger, emoji="🍎", custom_id="osu_btn_ctb")
    async def ctb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_mode_embed(self.osu_name, self.osu_user_id, 2, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Mania", style=discord.ButtonStyle.secondary, emoji="🎹", custom_id="osu_btn_mania")
    async def mania_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_mode_embed(self.osu_name, self.osu_user_id, 3, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)


# ========================================================
# 📊 四模式玩家數據總覽
# ========================================================
def generate_profile_embed(osu_name, osu_user_id, mode_id, author_mention, author_avatar_url, rank_track_id=None):
    """抓取特定模式的玩家整體數據並生成 Embed。
    rank_track_id：綁定該 osu! 帳號的 Discord user id，用來跟上次查詢的全球排名比較升降。"""
    mode_key, mode_name = OSU_MODES[mode_id]

    embed = discord.Embed(
        title=f"📊 {osu_name} 的玩家數據總覽",
        color=discord.Color.from_rgb(255, 102, 170)
    )

    osu_profile_link = f"https://osu.ppy.sh/users/{osu_user_id if osu_user_id else osu_name}"
    embed.description = (
        f"✨ **伺服器成員**：{osu_name}\n"
        f"• **Discord 帳號**：{author_mention}\n"
        f"• **osu! 個人檔案**：[點擊前往個人主頁]({osu_profile_link})\n"
        f"──────────────────"
    )

    if osu_user_id:
        embed.set_thumbnail(url=f"https://a.ppy.sh/{osu_user_id}")
    else:
        embed.set_thumbnail(url=author_avatar_url)

    try:
        lookup_target = osu_user_id if osu_user_id else osu_name
        lookup_key = "id" if osu_user_id else "username"
        user = osu_api.user(lookup_target, mode=mode_key, key=lookup_key)
        stats = user.statistics

        if not stats:
            embed.add_field(name="提示", value="```ansi\n[1;30m* 目前沒有此模式的數據 *[0m\n```", inline=False)
            return embed

        pp_raw = stats.pp or 0.0
        raw_global_rank = stats.global_rank
        global_rank = raw_global_rank if raw_global_rank is not None else "N/A"
        country_rank = stats.country_rank if stats.country_rank is not None else "N/A"
        accuracy = stats.hit_accuracy or 0.0

        # 🔺 排名變化追蹤：跟上次查詢時記錄的全球排名比較
        rank_change_text = ""
        if rank_track_id is not None and raw_global_rank is not None:
            rank_history_ref = db.reference(f'users/{rank_track_id}/last_rank/{mode_key}')
            prev_rank = rank_history_ref.get()
            if isinstance(prev_rank, int) and prev_rank != raw_global_rank:
                diff = abs(prev_rank - raw_global_rank)
                if prev_rank > raw_global_rank:
                    rank_change_text = f" (▲{diff:,})"
                else:
                    rank_change_text = f" (▼{diff:,})"
            rank_history_ref.set(raw_global_rank)
        level = stats.level.current if stats.level else 0
        playcount = stats.play_count or 0
        ranked_score = stats.ranked_score or 0
        total_score = stats.total_score or 0
        count300 = stats.count_300 or 0
        count100 = stats.count_100 or 0
        count50 = stats.count_50 or 0
        countmiss = stats.count_miss or 0
        total_hits = count300 + count100 + count50 + countmiss
        s_counts = stats.grade_counts.s if stats.grade_counts else 0
        a_counts = stats.grade_counts.a if stats.grade_counts else 0

        embed.add_field(
            name=f"📊 {mode_name}",
            value=(
                f"**PP：** {pp_raw:,.1f}\n"
                f"**全球排名：** #{global_rank}{rank_change_text}\n"
                f"**國家排名：** #{country_rank}\n"
                f"**精準度：** {accuracy:.2f}%\n"
                f"**等級：** Lv.{level}"
            ),
            inline=False
        )

        embed.add_field(
            name="🎯 遊玩數據",
            value=(
                f"**遊玩次數：** {playcount:,}\n"
                f"**Ranked 分數：** {ranked_score:,}\n"
                f"**總分數：** {total_score:,}\n"
                f"**總命中數：** {total_hits:,}\n"
                f"**S/A 次數：** {s_counts:,} / {a_counts:,}"
            ),
            inline=False
        )

        hit_counts_text = (
            f"```ansi\n"
            f"[1;37mHit 分佈 ({mode_name})[0m\n"
            f"300: [1;32m{count300:>10,}[0m\n"
            f"100: [1;33m{count100:>10,}[0m\n"
            f" 50: [1;36m{count50:>10,}[0m\n"
            f"Miss: [1;31m{countmiss:>10,}[0m"
            f"```"
        )

        embed.add_field(name="🔢 命中分佈", value=hit_counts_text, inline=False)

    except Exception as e:
        print(f"generate_profile_embed 失敗: {e}")
        embed.add_field(name="錯誤", value="```ansi\n[1;31m❌ 連線官方 API 失敗[0m\n```", inline=False)

    embed.set_footer(text=f"osu! API v2 | {mode_name}")
    return embed


class OsuProfileView(discord.ui.View):
    def __init__(self, ctx, osu_name, osu_user_id, target_member=None):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.osu_name = osu_name
        self.osu_user_id = osu_user_id
        # 被查詢的成員（沒指定時就是查詢者自己），用來顯示 mention/頭像並記錄排名歷史
        self.target_member = target_member or ctx.author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ 這不是你的對話面板，請自己輸入 `!profile` 查詢喔！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Standard", style=discord.ButtonStyle.primary, emoji="⭕", custom_id="profile_btn_std")
    async def std_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 0, self.target_member.mention, self.target_member.display_avatar.url, rank_track_id=self.target_member.id)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Taiko", style=discord.ButtonStyle.success, emoji="🥁", custom_id="profile_btn_taiko")
    async def taiko_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 1, self.target_member.mention, self.target_member.display_avatar.url, rank_track_id=self.target_member.id)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Catch", style=discord.ButtonStyle.danger, emoji="🍎", custom_id="profile_btn_ctb")
    async def ctb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 2, self.target_member.mention, self.target_member.display_avatar.url, rank_track_id=self.target_member.id)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Mania", style=discord.ButtonStyle.secondary, emoji="🎹", custom_id="profile_btn_mania")
    async def mania_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 3, self.target_member.mention, self.target_member.display_avatar.url, rank_track_id=self.target_member.id)
        await interaction.message.edit(embed=new_embed, view=self)


# ========================================================
# ⚙️ 核心 Cog 類別
# ========================================================
class OsuCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _lookup_osu_user_id(self, osu_name):
        """依 username 查 osu! user id，查不到就回傳 None（帳號可能改名/不存在）"""
        try:
            user = osu_api.user(osu_name, key="username")
            return user.id
        except Exception:
            return None

    # 1. 指令 !link
    @commands.hybrid_command(name="link", description="綁定你的 osu! 帳號")
    @app_commands.describe(osu_name="你的 osu! 帳號名稱")
    async def link(self, ctx, *, osu_name: str = None):
        if not osu_name:
            await ctx.send(embed=error_embed("使用方法錯誤！請輸入：`!link [你的 osu! 帳號名稱]`"))
            return

        user_id = str(ctx.author.id)
        try:
            ref = db.reference(f'users/{user_id}')
            ref.set({
                'discord_mention': ctx.author.mention,
                'osu_name': osu_name
            })

            embed = discord.Embed(
                title="✅ 帳號綁定成功！",
                description=f"已成功將 {ctx.author.mention} 綁定至 osu! 帳號：**{osu_name}** 🌟\n現在你可以輸入 `!top` 查看戰績！",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(embed=error_embed(f"寫入資料庫失敗，錯誤原因: {e}"))

    def _no_link_embed(self, ctx, target):
        if target:
            return error_embed(f"**{target.display_name}** 還沒有綁定 osu! 帳號。")
        return error_embed(f"{ctx.author.mention} 你還沒有綁定帳號喔！請先使用 `!link [你的 osu! 帳號]`")

    # 2. 指令 !top（可選：!top @成員 查詢別人）
    @commands.hybrid_command(name="top", description="查看戰績 Top 1-5（不指定就查自己）")
    @app_commands.describe(target="要查詢的成員（可省略，預設查自己）")
    async def top(self, ctx, target: discord.Member = None):
        lookup_member = target or ctx.author
        ref = db.reference(f'users/{lookup_member.id}')
        user_data = ref.get()

        if not user_data:
            await ctx.send(embed=self._no_link_embed(ctx, target))
            return

        osu_name = user_data.get('osu_name')
        osu_user_id = self._lookup_osu_user_id(osu_name)

        embed = discord.Embed(
            title=f"🏆 {osu_name} 的戰績主頁面",
            description=(
                f"✨ **{'歡迎回來！' if not target else f'{lookup_member.display_name} 的戰績查詢'}**\n\n"
                f"• **Discord 帳號**：{lookup_member.mention}\n"
                f"• **osu! 綁定帳號**：**{osu_name}**\n"
                f"• **個人檔案**：[點擊前往個人主頁](https://osu.ppy.sh/users/{osu_user_id if osu_user_id else osu_name})\n\n"
                f"📥 **請點擊下方的按鈕**，即可動態查看該模式的 Top 1-5 最佳表現！"
            ),
            color=discord.Color.from_rgb(255, 102, 170)
        )

        if osu_user_id:
            embed.set_thumbnail(url=f"https://a.ppy.sh/{osu_user_id}")
        else:
            embed.set_thumbnail(url=lookup_member.display_avatar.url)

        view = OsuModeView(ctx, osu_name, osu_user_id)
        await ctx.send(embed=embed, view=view)

    # 2.5 指令 !profile（四模式玩家數據總覽，可選：!profile @成員 查詢別人）
    @commands.hybrid_command(name="profile", aliases=["pf"], description="四模式玩家數據總覽（不指定就查自己）")
    @app_commands.describe(target="要查詢的成員（可省略，預設查自己）")
    async def profile(self, ctx, target: discord.Member = None):
        lookup_member = target or ctx.author
        ref = db.reference(f'users/{lookup_member.id}')
        user_data = ref.get()

        if not user_data:
            await ctx.send(embed=self._no_link_embed(ctx, target))
            return

        osu_name = user_data.get('osu_name')
        osu_user_id = self._lookup_osu_user_id(osu_name)

        embed = generate_profile_embed(osu_name, osu_user_id, 0, lookup_member.mention, lookup_member.display_avatar.url, rank_track_id=lookup_member.id)
        view = OsuProfileView(ctx, osu_name, osu_user_id, target_member=lookup_member)
        await ctx.send(embed=embed, view=view)

    # 3. 指令 !compare
    @commands.hybrid_command(name="compare", aliases=["c"], description="跟指定成員比較四模式 PP")
    @app_commands.describe(target="要比較的對象")
    async def compare(self, ctx, target: discord.Member = None):
        if not target:
            await ctx.send(embed=error_embed("使用方法錯誤！請標記你想對比的對象，例如：`!compare @成員名稱`"))
            return

        my_data = db.reference(f'users/{ctx.author.id}').get()
        target_data = db.reference(f'users/{target.id}').get()

        if not my_data or not my_data.get('osu_name'):
            await ctx.send(embed=self._no_link_embed(ctx, None))
            return
        if not target_data or not target_data.get('osu_name'):
            await ctx.send(embed=self._no_link_embed(ctx, target))
            return

        my_name = my_data.get('osu_name')
        target_name = target_data.get('osu_name')

        await ctx.send(f"⏳ 正在讀取並計算兩位玩家的最新四模式數據...")

        def get_all_modes_pp(osu_name):
            pp_list = [0.0, 0.0, 0.0, 0.0]
            for mode_id, (mode_key, _) in OSU_MODES.items():
                try:
                    user = osu_api.user(osu_name, mode=mode_key, key="username")
                    if user.statistics:
                        pp_list[mode_id] = user.statistics.pp or 0.0
                except Exception:
                    pass
            return pp_list

        my_pp = get_all_modes_pp(my_name)
        target_pp = get_all_modes_pp(target_name)

        my_total = sum(my_pp)
        target_total = sum(target_pp)

        # 回寫進 Firebase 供排行榜使用
        db.reference(f'users/{ctx.author.id}/modes_pp').set(my_pp)
        db.reference(f'users/{ctx.author.id}/total_pp').set(my_total)
        db.reference(f'users/{target.id}/modes_pp').set(target_pp)
        db.reference(f'users/{target.id}/total_pp').set(target_total)

        embed = discord.Embed(
            title="⚔️ 玩家實力大對決",
            color=discord.Color.gold(),
            description=f"**{my_name}** vs  **{target_name}**\n──────────────────"
        )

        ansi_text = "```ansi\n"
        ansi_text += f"模式         | {my_name[:10]:<10} | {target_name[:10]:<10}\n"
        ansi_text += "-------------+------------+------------\n"

        modes_label = ["⭕ Standard ", "🥁 Taiko    ", "🍎 Catch    ", "🎹 Mania    "]
        my_wins = 0
        target_wins = 0
        for i in range(4):
            if my_pp[i] > target_pp[i]:
                p1_str = f"[1;32m{my_pp[i]:>8.1f}[0m"
                p2_str = f"[1;31m{target_pp[i]:>8.1f}[0m"
                my_wins += 1
            elif my_pp[i] < target_pp[i]:
                p1_str = f"[1;31m{my_pp[i]:>8.1f}[0m"
                p2_str = f"[1;32m{target_pp[i]:>8.1f}[0m"
                target_wins += 1
            else:
                p1_str = f"{my_pp[i]:>8.1f}"
                p2_str = f"{target_pp[i]:>8.1f}"

            ansi_text += f"{modes_label[i]} | {p1_str} | {p2_str}\n"

        ansi_text += "-------------+------------+------------\n"
        ansi_text += f"🏆 綜合總PP  | [1;35m{my_total:>8.1f}[0m | [1;35m{target_total:>8.1f}[0m\n"
        ansi_text += "```"

        embed.add_field(name="📊 四模式數據對比表", value=ansi_text, inline=False)

        if my_total > target_total:
            summary = f"🏆 **{my_name}** 贏了 {my_wins}/4 個模式，總 PP 領先 **{target_name}** {my_total - target_total:,.1f} pp！"
        elif target_total > my_total:
            summary = f"🏆 **{target_name}** 贏了 {target_wins}/4 個模式，總 PP 領先 **{my_name}** {target_total - my_total:,.1f} pp！"
        else:
            summary = f"🤝 **{my_name}** 與 **{target_name}** 總 PP 打成平手！"
        embed.add_field(name="🎯 結論", value=summary, inline=False)

        await ctx.send(embed=embed)

    # 4. 指令 !leaderboard
    @commands.hybrid_command(name="leaderboard", aliases=["lb"], description="伺服器四模式綜合 PP 排行榜 Top 10")
    async def leaderboard(self, ctx):
        all_users = db.reference('users').get()
        if not all_users:
            await ctx.send(embed=error_embed("目前資料庫中沒有任何玩家數據。"))
            return

        leaderboard_list = []
        for user_id, user_data in all_users.items():
            osu_name = user_data.get('osu_name', '未知')
            total_pp = user_data.get('total_pp', 0.0)
            modes_pp = user_data.get('modes_pp', [0.0, 0.0, 0.0, 0.0])

            if total_pp > 0:
                leaderboard_list.append({
                    'osu_name': osu_name,
                    'total_pp': total_pp,
                    'modes_pp': modes_pp
                })

        if not leaderboard_list:
            await ctx.send(embed=info_embed("💡 尚未有人進行過 `!compare`，排行榜尚無數據，請先使用 `!compare` 來初始化分數！"))
            return

        leaderboard_list.sort(key=lambda x: x['total_pp'], reverse=True)

        embed = discord.Embed(
            title="🏆 伺服器四模式綜合實力排行榜 (Top 10)",
            color=discord.Color.from_rgb(255, 102, 170),
            description="本排行依據各成員之 (Std + Taiko + Catch + Mania) 總 PP 加總進行排名。\n──────────────────"
        )

        lb_text = "```ansi\n"
        lb_text += "名次 | 玩家名稱           | 綜合總 PP \n"
        lb_text += "-----+--------------------+-----------\n"

        for index, player in enumerate(leaderboard_list[:10]):
            rank = index + 1
            name = player['osu_name']
            total = player['total_pp']

            if rank == 1:
                rank_str = f"[1;33m🥇 [0m"
            elif rank == 2:
                rank_str = f"[1;36m🥈 [0m"
            elif rank == 3:
                rank_str = f"[1;31m🥉 [0m"
            else:
                rank_str = f"#{rank:<2}"

            lb_text += f"{rank_str} | {name:<18} | {total:>8.1f}\n"

        lb_text += "```"
        embed.add_field(name="📈 即時排名（前 10 名）", value=lb_text, inline=False)
        embed.set_footer(text="💡 想讓自己上榜或更新分數嗎？請與任意成員輸入一次 !compare 即可！")

        await ctx.send(embed=embed)

    # 5. 指令 !collections（查詢在 osu-花火網頁 發布的圖庫收藏，可選：查別人）
    @commands.hybrid_command(name="collections", aliases=["col"], description="查詢在 osu-花火網頁 上發布的圖庫收藏摘要")
    @app_commands.describe(target="要查詢的成員（可省略，預設查自己）")
    async def collections_cmd(self, ctx, target: discord.Member = None):
        lookup_member = target or ctx.author
        ref = db.reference(f'users/{lookup_member.id}')
        user_data = ref.get()

        if not user_data:
            await ctx.send(embed=self._no_link_embed(ctx, target))
            return

        osu_name = user_data.get('osu_name')

        try:
            entry = fetch_collection_summary(osu_name)
        except Exception as e:
            print(f"collections-list 查詢失敗: {e}")
            await ctx.send(embed=error_embed("連線 osu-花火網頁 失敗，請稍後再試。"))
            return

        if not entry:
            await ctx.send(embed=info_embed(f"💨 **{osu_name}** 目前還沒有在 osu-花火網頁 上發布圖庫收藏喔！"))
            return

        tags = entry.get("tags") or []
        tags_text = "、".join(tags[:8]) + ("...等" if len(tags) > 8 else "") if tags else "（無標籤）"
        updated_at = (entry.get("updatedAt") or "")[:10]

        embed = discord.Embed(
            title=f"📚 {entry.get('username')} 的圖庫收藏",
            url="https://osu-collection-hanabi.netlify.app/",
            description=f"在網站的「收藏廣場」搜尋 **{entry.get('username')}** 就能看到完整收藏內容",
            color=discord.Color.from_rgb(255, 102, 170)
        )
        embed.add_field(name="收藏套數", value=f"{entry.get('totalSets', 0):,}", inline=True)
        embed.add_field(name="最高星數", value=f"{entry.get('maxRating', 0):.2f} ⭐", inline=True)
        embed.add_field(name="❤️ 讚數", value=f"{entry.get('likeCount', 0)}", inline=True)
        embed.add_field(name="曲風標籤", value=tags_text, inline=False)
        embed.set_footer(text=f"最後更新：{updated_at}｜資料來源：osu-花火網頁")

        await ctx.send(embed=embed)

    # 6. 指令 !help（指令選單）
    @commands.hybrid_command(name="help", aliases=["menu", "指令"], description="顯示 Osu Bot 的指令選單")
    async def help_command(self, ctx):
        embed = discord.Embed(
            title="📖 Osu Bot 指令選單",
            description="以下是目前可以使用的指令：\n──────────────────",
            color=discord.Color.from_rgb(255, 102, 170)
        )
        embed.add_field(name="`!link [osu!帳號]`", value="綁定你的 osu! 帳號", inline=False)
        embed.add_field(name="`!top [@成員]`", value="查看戰績 Top 1-5（不指定就查自己，也可以 `!top @成員` 查別人）", inline=False)
        embed.add_field(name="`!profile [@成員]`（別名 `!pf`）", value="四模式玩家數據總覽（PP、排名、精準度、命中分佈），一樣可以查別人", inline=False)
        embed.add_field(name="`!compare @成員`（別名 `!c`）", value="跟指定成員比較四模式 PP", inline=False)
        embed.add_field(name="`!leaderboard`（別名 `!lb`）", value="伺服器四模式綜合 PP 排行榜 Top 10", inline=False)
        embed.add_field(name="`!collections [@成員]`（別名 `!col`）", value="查詢在 osu-花火網頁 上發布的圖庫收藏摘要，一樣可以查別人", inline=False)
        embed.set_footer(text="🎀 想再看一次這份選單，隨時輸入 !help")
        await ctx.send(embed=embed)

# 載入 Cog 到主程式
async def setup(bot):
    await bot.add_cog(OsuCommands(bot))
