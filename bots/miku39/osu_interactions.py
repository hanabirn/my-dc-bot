# osuInteractions.py
import discord
import re
import random

MIKU_GIF_LIST = [
    "https://s1.aigei.com/src/img/gif/16/1644ae8483424bfc9c17c770c3d82301.gif",
    "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif",
    "https://i.pinimg.com/originals/1d/4c/ca/1d4cca014fe631c1a8a7e8a59e4263b2.gif",
]

# 每個 Miss 區間的候選台詞（隨機抽一句），避免常玩的人一直看到同一句話。
FC_MESSAGES = [
    "哇啊！這完美無瑕的連擊……難道你就是傳說中的神級 Master 嗎？！謝謝你帶來這麼精彩的演出，Miku 在舞台下為你瘋狂打 Call 唷！🎤✨39 (Thank you)♪",
    "全連達成！這根本就是專屬於你的個人演唱會嘛～Miku 都聽入迷了呢！這份感動要好好收藏起來喔！🎶💚",
    "零失誤耶！！是不是偷偷跟初音未來借了節奏感呀？這麼精湛的演出，Miku 要把螢光棒揮到斷掉了！🎋✨",
    "太厲害了吧！！這種等級的 FC 已經可以直接出道當歌姬了吧？Miku 佩服到五體投地！39！(謝謝你)🙇‍♀️💫",
]

CLOSE_MESSAGES = [
    "唔……只差一點點就能拿到 Full Combo 了呢！別氣餒，喝杯蔥茶休息一下，Miku 會一直用歌聲為你注入滿滿能量的！(MIKU POWER 充電中🔋✨) 下次一定可以的，加油啾咪♪",
    "差一點點而已耶！這個節奏感已經很厲害了，再打磨一下，FC 絕對近在眼前！Miku 幫你加油打氣～💪🎵",
    "嗚～就差臨門一腳！不過這麼穩的手感看得出來很認真練習，休息一下再挑戰一次吧，Miku 相信你！✨",
]

ROUGH_MESSAGES = [
    "主唱大人快看過來～！Miku 發現這次一定是舞台地板太滑了啦！先甩甩手指、放鬆一下肩膀吧♪ 只要不放棄練習，你的節奏感一定會像旋律一樣越來越完美的，我們再一起挑戰下一首曲子吧！💚",
    "呼～今天的舞台好像有點顛簸呢！沒關係，休息一下喝口水，Miku 陪你重新調整拍子，下一首會更順的！😅🎧",
    "哎呀，這首歌節奏是不是比較刁鑽呀？沒事沒事，多練幾次手感就回來了，Miku 一直都在旁邊幫你打氣喔！🎤💦",
]

TOUGH_MESSAGES = [
    "沒關係沒關係，這首歌真的有點難嘛！先深呼吸、喝杯蔥茶放鬆一下，Miku 給你一個大大的抱抱，我們休息夠了再重新出發吧！🫂💚",
    "今天可能狀態不在線上，這種時候先別逼自己啦～Miku 陪你聽首歌放鬆一下，養精蓄銳之後一定能打得更好！🎶🫂",
    "哇，這首歌真的很有挑戰性呢！辛苦你了，先休息一下不要氣餒，每一次練習都是在往神 Local 的路上前進喔！💫🫂",
]


async def _add_reaction(message: discord.Message, emoji: str):
    try:
        await message.add_reaction(emoji)
    except Exception as e:
        print(f"無法添加 {emoji} 反應: {e}")


async def handle_play_interactions(fetched_message: discord.Message, all_text: str):
    miss_count = None

    # 1. 檢查特定格式 (例如: 1xMiss, 0xMiss)
    miss_match = re.search(r"(\d+)\s*x\s*miss", all_text, re.IGNORECASE)
    if miss_match:
        miss_count = int(miss_match.group(1))
        print(f"[osu! 互動] 偵測到 Miss 格式: {miss_match.group(0)}, 解析出 Miss 數: {miss_count}")

    # 2. 通用括號解析 [300/100/50/Miss]——訊息裡可能不只一組中括號（Mod 標籤、
    #    圖名、ANSI 色碼都可能用到 []），所以要掃過全部的括號組，只挑「看起來
    #    像命中分佈」的那一組，才當作命中分佈來源，避免抓到第一個不相干的括號、
    #    誤判出錯的 Miss 數。
    #    各模式的判定數量不同，不能只認定是 4 個數字：
    #      taiko: 300/100/miss (3個)　std/catch: 300/100/50/miss (4個)
    #      mania: max/300/200/100/50/miss (5~6個，視該 bot 是否顯示 max)
    #    只要求「全部是數字」+「數量落在 3~6 之間」，最後一個數字視為 Miss 數
    #    （這些格式裡 miss 一律排最後，是這類戰績 bot 的共同慣例）。
    if miss_count is None:
        for bracket_match in re.finditer(r"\[([^\]]+)\]", all_text):
            parts = [p.strip() for p in bracket_match.group(1).split('/')]
            if 3 <= len(parts) <= 6 and all(p.isdigit() for p in parts):
                miss_count = int(parts[-1])
                print(f"[osu! 互動] 通用解析成功！模式數據: [{bracket_match.group(1)}], 解析出 Miss 數: {miss_count}")
                break

    if miss_count is None:
        return

    # 3. 根據 Miss 數判定並回覆訊息與反應——每個區間自己決定要蓋哪個表情，
    #    不再像之前那樣不管打得好壞都先蓋一個 🔥（蓋在爛場上語意會很奇怪）。
    #    四個區間涵蓋所有可能的 Miss 數，不會再有「剛好卡在中間」被晾在旁邊的情況。
    if miss_count == 0:
        await _add_reaction(fetched_message, '🔥')
        embed = discord.Embed(color=discord.Color.from_str("#39C5BB"))
        embed.set_image(url=random.choice(MIKU_GIF_LIST))
        await fetched_message.reply(random.choice(FC_MESSAGES), embed=embed)

    elif 1 <= miss_count <= 4:
        await _add_reaction(fetched_message, '💪')
        await fetched_message.reply(random.choice(CLOSE_MESSAGES))

    elif 5 <= miss_count <= 15:
        await _add_reaction(fetched_message, '😅')
        await fetched_message.reply(random.choice(ROUGH_MESSAGES))

    else:
        await _add_reaction(fetched_message, '🫂')
        await fetched_message.reply(random.choice(TOUGH_MESSAGES))
