# mikuCommands.py
import discord
import random
import json
import os
from googleSearch import BEAUTY_IMAGES

DATA_FILE = "userPools.json"

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

async def handle_miku_commands(message: discord.Message, bot):
    msg_str = message.content.strip()
    user_id = str(message.author.id)

    # 1. 運勢指令
    if msg_str == "bot 運勢":
        fortune = random.choice(FORTUNE_LIST)
        embed = discord.Embed(
            title=f"🎤 Miku39 占卜結果：{fortune['type']}",
            description=fortune['desc'],
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=fortune['gif'])
        await message.reply(embed=embed)
        return True

    # 2. 抽卡指令
    elif msg_str == "bot 抽卡":
        img_url = random.choice(BEAUTY_IMAGES)
        embed = discord.Embed(
            title="🎤 世界第一公主殿下 美圖抽卡 ♪",
            description="點擊按鈕或輸入指令可以收藏到珍藏庫喔！",
            color=discord.Color.from_str("#39C5BB")
        )
        embed.set_image(url=img_url)

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

        await message.reply(embed=embed, view=CollectView(img_url))
        return True

    # 3. 珍藏庫指令
    elif msg_str == "bot 珍藏庫":
        data = load_user_data()
        user_cards = data.get(user_id, [])

        if not user_cards:
            await message.reply("💨 你的珍藏庫目前空空如也呢！快使用 `bot 抽卡` 來收集公主殿下的美圖吧！")
            return True

        view = PoolView(message.author.id, user_cards)
        await message.reply(embed=view.get_embed(), view=view)
        return True

    return False