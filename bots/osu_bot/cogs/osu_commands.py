import os
import discord
from discord.ext import commands
import requests
from firebase_admin import db

# ========================================================
# 機器人核心設定與常數
# ========================================================
# 🎯 填入你的本地測試金鑰（推進 GitHub 前記得清空喔！）
LOCAL_API_KEY = "" 

OSU_API_KEY = os.getenv("OSU_API_KEY", LOCAL_API_KEY)

# 🎯 已修正：按鈕與顯示的櫻花全部改為對應符號
OSU_MODES = {
    0: "⭕ osu! Standard (標準模式)",
    1: "🥁 osu! Taiko (太鼓模式)",
    2: "🍎 osu! Catch (接水果模式)",
    3: "🎹 osu! Mania (狂熱模式)"
}

RANK_ANSI_STRINGS = {
    "X": "\u001b[1;33mSS\u001b[0m",     # 金色 SS
    "XH": "\u001b[1;36mSS\u001b[0m",    # Iron SS (白銀色)
    "S": "\u001b[1;33mS\u001b[0m",      # 金色 S
    "SH": "\u001b[1;36mS\u001b[0m",     # Iron S (白銀色)
    "A": "\u001b[1;32mA\u001b[0m",      # 綠色 A
    "B": "\u001b[1;34mB\u001b[0m",      # 藍色 B
    "C": "\u001b[1;33mC\u001b[0m",      # 黃色 C
    "D": "\u001b[1;31mD\u001b[0m"       # 紅色 D
}

# ========================================================
# 🛠️ 核心工具函式
# ========================================================
def parse_mods(mods_int):
    """將 osu! API 的 mods 整數轉換成對應的縮寫（例如：HDDT）"""
    if not mods_int or int(mods_int) == 0:
        return "NM"

    mods_int = int(mods_int)
    mod_map = {
        1: "NF", 2: "EZ", 4: "TD", 8: "HD", 16: "HR", 
        32: "SD", 64: "DT", 128: "RL", 256: "HT", 
        512: "NC", 1024: "FL", 2048: "Autoplay", 4096: "SO",
        16384: "PF", 1048576: "MR"
    }
    
    active_mods = []
    for mod_value, mod_name in mod_map.items():
        if mods_int & mod_value:
            if mod_name == "DT" and (mods_int & 512):
                continue
            active_mods.append(mod_name)
            
    return "".join(active_mods) if active_mods else "NM"


def generate_mode_embed(osu_name, osu_user_id, mode_id, author_mention, author_avatar_url):
    """抓取特定模式的 Top 5 並生成對應 Embed（含各模式 ACC 計算）"""
    mode_name = OSU_MODES[mode_id]
    
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

    api_url = f"https://osu.ppy.sh/api/get_user_best?k={OSU_API_KEY}&u={osu_name}&m={mode_id}&limit=5&type=string"
    
    try:
        response = requests.get(api_url)
        best_plays = response.json()
        
        if not best_plays or "error" in best_plays or not isinstance(best_plays, list):
            embed.add_field(name="提示", value="```ansi\n\u001b[1;30m* 目前沒有此模式的遊玩紀錄 *\u001b[0m\n```", inline=False)
            return embed
        
        for index, play in enumerate(best_plays):
            beatmap_id = play.get('beatmap_id', 'Unknown')
            pp = float(play.get('pp', 0) or 0)
            raw_rank = play.get('rank', 'F')
            
            mods_value = play.get('enabled_mods', 0)
            mods_text = parse_mods(mods_value)
            
            # --- 🎯 各模式 ACC 計算邏輯 ---
            c300 = int(play.get('count300', 0) or 0)
            c100 = int(play.get('count100', 0) or 0)
            c50 = int(play.get('count50', 0) or 0)
            cmiss = int(play.get('countmiss', 0) or 0)
            cgeki = int(play.get('countgeki', 0) or 0)
            ckatu = int(play.get('countkatu', 0) or 0)
            
            acc = 0.0
            if mode_id == 0:    # Standard
                total_hits = cmiss + c50 + c100 + c300
                if total_hits > 0:
                    acc = ((c50 * 50 + c100 * 100 + c300 * 300) / (total_hits * 300)) * 100
            elif mode_id == 1:  # Taiko
                total_hits = cmiss + c100 + c300
                if total_hits > 0:
                    acc = ((c100 * 0.5 + c300) / total_hits) * 100
            elif mode_id == 2:  # Catch
                total_hits = cmiss + c50 + c100 + c300 + ckatu
                if total_hits > 0:
                    acc = ((c50 + c100 + c300) / total_hits) * 100
            elif mode_id == 3:  # Mania
                total_hits = cmiss + c50 + c100 + ckatu + c300 + cgeki
                if total_hits > 0:
                    acc = ((c50 * 50 + c100 * 100 + ckatu * 200 + c300 * 300 + cgeki * 300) / (total_hits * 300)) * 100
            
            map_title = "未知譜面歌曲"
            map_version = "未知難度"
            try:
                map_url = f"https://osu.ppy.sh/api/get_beatmaps?k={OSU_API_KEY}&b={beatmap_id}"
                map_data = requests.get(map_url).json()
                if map_data and isinstance(map_data, list) and len(map_data) > 0:
                    map_title = map_data[0].get('title', '未知譜面歌曲')
                    map_version = map_data[0].get('version', '未知難度')
            except Exception:
                pass
            
            clean_title = map_title.replace('[', '［').replace(']', '］')
            clean_version = map_version.replace('[', '［').replace(']', '］')
            download_link = f"https://osu.ppy.sh/b/{beatmap_id}"
            
            field_value = f"🎵 {clean_title} ［{clean_version}］\n"
            field_value += f"🔗 譜面連結: <{download_link}>\n"
            
            colored_rank = RANK_ANSI_STRINGS.get(raw_rank.upper(), f"{raw_rank}")
            
            # 🎯 完美橫向排列不留空行：加入高亮 ACC 顯示
            field_value += "```ansi\n"
            field_value += f"🎖️ \u001b[1;30m資訊\u001b[0m | 譜面ID: \u001b[1;30m{beatmap_id:<8}\u001b[0m | \u001b[1;35m{pp:>6.2f} PP\u001b[0m | \u001b[1;36m{acc:>6.2f}%\u001b[0m | {colored_rank} \u001b[1;37m({mods_text})\u001b[0m```"
            
            embed.add_field(
                name=f"#{index+1} 最佳表現",
                value=field_value,
                inline=False
            )
    except Exception:
        embed.add_field(name="錯誤", value="```ansi\n\u001b[1;31m❌ 連線官方 API 失敗\u001b[0m\n```", inline=False)
        
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
def generate_profile_embed(osu_name, osu_user_id, mode_id, author_mention, author_avatar_url):
    """抓取特定模式的玩家整體數據並生成 Embed"""
    mode_name = OSU_MODES[mode_id]

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

    api_url = f"https://osu.ppy.sh/api/get_user?k={OSU_API_KEY}&u={osu_name}&m={mode_id}&type=string"

    try:
        response = requests.get(api_url)
        user_data = response.json()

        if not user_data or "error" in user_data or not isinstance(user_data, list) or len(user_data) == 0:
            embed.add_field(name="提示", value="```ansi\n\u001b[1;30m* 目前沒有此模式的數據 *\u001b[0m\n```", inline=False)
            return embed

        u = user_data[0]

        pp_raw = float(u.get('pp_raw', 0) or 0)
        global_rank = u.get('pp_rank', 'N/A')
        country_rank = u.get('pp_country_rank', 'N/A')
        accuracy = float(u.get('accuracy', 0) or 0)
        level = u.get('level', '0')
        playcount = int(u.get('playcount', 0) or 0)
        ranked_score = int(u.get('ranked_score', 0) or 0)
        total_score = int(u.get('total_score', 0) or 0)
        count300 = int(u.get('count300', 0) or 0)
        count100 = int(u.get('count100', 0) or 0)
        count50 = int(u.get('count50', 0) or 0)
        countmiss = int(u.get('countmiss', 0) or 0)
        countgeki = int(u.get('countgeki', 0) or 0)
        countkatu = int(u.get('countkatu', 0) or 0)
        total_hits = count300 + count100 + count50 + countmiss
        s_counts = int(u.get('count_rank_s', 0) or 0)
        a_counts = int(u.get('count_rank_a', 0) or 0)

        embed.add_field(
            name=f"📊 {mode_name}",
            value=(
                f"**PP：** {pp_raw:,.1f}\n"
                f"**全球排名：** #{global_rank}\n"
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
            f"\u001b[1;37mHit 分佈 ({mode_name})\u001b[0m\n"
            f"300: \u001b[1;32m{count300:>10,}\u001b[0m\n"
            f"100: \u001b[1;33m{count100:>10,}\u001b[0m\n"
            f" 50: \u001b[1;36m{count50:>10,}\u001b[0m\n"
            f"Miss: \u001b[1;31m{countmiss:>10,}\u001b[0m"
        )

        if mode_id == 3:
            hit_counts_text += (
                f"\nMAX: \u001b[1;35m{countgeki:>10,}\u001b[0m\n"
                f"OK:  \u001b[1;34m{countkatu:>10,}\u001b[0m"
            )
        hit_counts_text += "```"

        embed.add_field(name="🔢 命中分佈", value=hit_counts_text, inline=False)

    except Exception:
        embed.add_field(name="錯誤", value="```ansi\n\u001b[1;31m❌ 連線官方 API 失敗\u001b[0m\n```", inline=False)

    embed.set_footer(text=f"osu! API v1 | {mode_name}")
    return embed


class OsuProfileView(discord.ui.View):
    def __init__(self, ctx, osu_name, osu_user_id):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.osu_name = osu_name
        self.osu_user_id = osu_user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ 這不是你的對話面板，請自己輸入 `!profile` 查詢喔！", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Standard", style=discord.ButtonStyle.primary, emoji="⭕", custom_id="profile_btn_std")
    async def std_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 0, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Taiko", style=discord.ButtonStyle.success, emoji="🥁", custom_id="profile_btn_taiko")
    async def taiko_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 1, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Catch", style=discord.ButtonStyle.danger, emoji="🍎", custom_id="profile_btn_ctb")
    async def ctb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 2, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)

    @discord.ui.button(label="Mania", style=discord.ButtonStyle.secondary, emoji="🎹", custom_id="profile_btn_mania")
    async def mania_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        new_embed = generate_profile_embed(self.osu_name, self.osu_user_id, 3, self.ctx.author.mention, self.ctx.author.display_avatar.url)
        await interaction.message.edit(embed=new_embed, view=self)


# ========================================================
# ⚙️ 核心 Cog 類別
# ========================================================
class OsuCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # 1. 指令 !link
    @commands.command(name="link")
    async def link(self, ctx, *, osu_name: str = None):
        if not osu_name:
            await ctx.send("❌ 使用方法錯誤！請輸入：`!link [你的 osu! 帳號名稱]`")
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
            await ctx.send(f"❌ 寫入資料庫失敗，錯誤原因: {e}")

    # 2. 指令 !top
    @commands.command(name="top")
    async def top(self, ctx):
        user_id = str(ctx.author.id)
        ref = db.reference(f'users/{user_id}')
        user_data = ref.get()
        
        if not user_data:
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有綁定帳號喔！請先使用 `!link [你的 osu! 帳號]`")
            return
            
        osu_name = user_data.get('osu_name')
        user_info_url = f"https://osu.ppy.sh/api/get_user?k={OSU_API_KEY}&u={osu_name}&type=string"
        osu_user_id = None
        
        try:
            user_response = requests.get(user_info_url).json()
            if user_response and isinstance(user_response, list) and len(user_response) > 0:
                osu_user_id = user_response[0].get('user_id')
        except Exception:
            pass

        embed = discord.Embed(
            title=f"🏆 {osu_name} 的戰績主頁面",
            description=(
                f"✨ **歡迎回來！**\n\n"
                f"• **Discord 帳號**：{ctx.author.mention}\n"
                f"• **osu! 綁定帳號**：**{osu_name}**\n"
                f"• **個人檔案**：[點擊前往個人主頁](https://osu.ppy.sh/users/{osu_user_id if osu_user_id else osu_name})\n\n"
                f"📥 **請點擊下方的按鈕**，即可動態查看該模式的 Top 1-5 最佳表現！"
            ),
            color=discord.Color.from_rgb(255, 102, 170)
        )
        
        if osu_user_id:
            embed.set_thumbnail(url=f"https://a.ppy.sh/{osu_user_id}")
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)

        view = OsuModeView(ctx, osu_name, osu_user_id)
        await ctx.send(embed=embed, view=view)

    # 2.5 指令 !profile（四模式玩家數據總覽）
    @commands.command(name="profile", aliases=["pf"])
    async def profile(self, ctx):
        user_id = str(ctx.author.id)
        ref = db.reference(f'users/{user_id}')
        user_data = ref.get()

        if not user_data:
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有綁定帳號喔！請先使用 `!link [你的 osu! 帳號]`")
            return

        osu_name = user_data.get('osu_name')
        user_info_url = f"https://osu.ppy.sh/api/get_user?k={OSU_API_KEY}&u={osu_name}&type=string"
        osu_user_id = None

        try:
            user_response = requests.get(user_info_url).json()
            if user_response and isinstance(user_response, list) and len(user_response) > 0:
                osu_user_id = user_response[0].get('user_id')
        except Exception:
            pass

        embed = generate_profile_embed(osu_name, osu_user_id, 0, ctx.author.mention, ctx.author.display_avatar.url)
        view = OsuProfileView(ctx, osu_name, osu_user_id)
        await ctx.send(embed=embed, view=view)

    # 3. 指令 !compare
    @commands.command(name="compare", aliases=["c"])
    async def compare(self, ctx, target: discord.Member = None):
        if not target:
            await ctx.send("❌ 使用方法錯誤！請標記你想對比的對象，例如：`!compare @成員名稱`")
            return

        my_data = db.reference(f'users/{ctx.author.id}').get()
        target_data = db.reference(f'users/{target.id}').get()

        if not my_data or not my_data.get('osu_name'):
            await ctx.send(f"❌ {ctx.author.mention} 你還沒有綁定帳號喔！請先使用 `!link`")
            return
        if not target_data or not target_data.get('osu_name'):
            await ctx.send(f"❌ 標記的成員 **{target.display_name}** 還沒有綁定 osu! 帳號。")
            return

        my_name = my_data.get('osu_name')
        target_name = target_data.get('osu_name')

        await ctx.send(f"⏳ 正在讀取並計算兩位玩家的最新四模式數據...")

        def get_all_modes_pp(osu_name):
            pp_list = [0.0, 0.0, 0.0, 0.0]
            for m in range(4):
                try:
                    url = f"https://osu.ppy.sh/api/get_user?k={OSU_API_KEY}&u={osu_name}&m={m}&type=string"
                    res = requests.get(url).json()
                    if res and isinstance(res, list) and len(res) > 0:
                        pp_list[m] = float(res[0].get('pp_raw', 0) or 0)
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
        for i in range(4):
            if my_pp[i] > target_pp[i]:
                p1_str = f"\u001b[1;32m{my_pp[i]:>8.1f}\u001b[0m"
                p2_str = f"\u001b[1;31m{target_pp[i]:>8.1f}\u001b[0m"
            elif my_pp[i] < target_pp[i]:
                p1_str = f"\u001b[1;31m{my_pp[i]:>8.1f}\u001b[0m"
                p2_str = f"\u001b[1;32m{target_pp[i]:>8.1f}\u001b[0m"
            else:
                p1_str = f"{my_pp[i]:>8.1f}"
                p2_str = f"{target_pp[i]:>8.1f}"
                
            ansi_text += f"{modes_label[i]} | {p1_str} | {p2_str}\n"
            
        ansi_text += "-------------+------------+------------\n"
        ansi_text += f"🏆 綜合總PP  | \u001b[1;35m{my_total:>8.1f}\u001b[0m | \u001b[1;35m{target_total:>8.1f}\u001b[0m\n"
        ansi_text += "```"

        embed.add_field(name="📊 四模式數據對比表", value=ansi_text, inline=False)
        await ctx.send(embed=embed)

    # 4. 指令 !leaderboard
    @commands.command(name="leaderboard", aliases=["lb"])
    async def leaderboard(self, ctx):
        all_users = db.reference('users').get()
        if not all_users:
            await ctx.send("❌ 目前資料庫中沒有任何玩家數據。")
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
            await ctx.send("💡 尚未有人進行過 `!compare`，排行榜尚無數據，請先使用 `!compare` 來初始化分數！")
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
                rank_str = f"\u001b[1;33m#{rank:<2}\u001b[0m"
            elif rank == 2:
                rank_str = f"\u001b[1;36m#{rank:<2}\u001b[0m"
            elif rank == 3:
                rank_str = f"\u001b[1;31m#{rank:<2}\u001b[0m"
            else:
                rank_str = f"#{rank:<2}"

            lb_text += f"{rank_str} | {name:<18} | {total:>8.1f}\n"

        lb_text += "```"
        embed.add_field(name="📈 即時排名（前 10 名）", value=lb_text, inline=False)
        embed.set_footer(text="💡 想讓自己上榜或更新分數嗎？請與任意成員輸入一次 !compare 即可！")
        
        await ctx.send(embed=embed)

# 載入 Cog 到主程式
async def setup(bot):
    await bot.add_cog(OsuCommands(bot))