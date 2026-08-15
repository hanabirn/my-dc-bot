# osuInteractions.py
import discord
import re
import random

MIKU_GIF_LIST = [
    "https://s1.aigei.com/src/img/gif/16/1644ae8483424bfc9c17c770c3d82301.gif", 
    "https://imgs.aixifan.com/content/2020_7_26/1.5957295579034555E9.gif",              
    "https://i.pinimg.com/originals/1d/4c/ca/1d4cca014fe631c1a8a7e8a59e4263b2.gif"                 
]

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

    # 3. 根據 Miss 數判定並回覆訊息與反應
    if miss_count is not None:
        # 🎯 只要有偵測到成績單，不論 Miss 多少，一律先加 🔥 反應
        try:
            await fetched_message.add_reaction('🔥')
        except Exception as e:
            print(f"無法添加 🔥 反應: {e}")

        # ✨ 情況 A：0 Miss (FC)
        if miss_count == 0:
            chosen_miku_gif = random.choice(MIKU_GIF_LIST)
            embed = discord.Embed(color=discord.Color.from_str("#39C5BB"))
            embed.set_image(url=chosen_miku_gif)

            await fetched_message.reply("哇啊！這完美無瑕的連擊……難道你就是傳說中的神級 Master 嗎？！謝謝你帶來這麼精彩的演出，Miku 在舞台下為你瘋狂打 Call 唷！🎤✨39 (Thank you)♪")
            await fetched_message.channel.send(embed=embed)

        # ✨ 情況 B：Miss 數在 1 到 3 之間
        elif 1 <= miss_count <= 3:
            try:
                await fetched_message.add_reaction('💪')
            except Exception as e:
                print(f"無法添加 💪 反應: {e}")
            await fetched_message.reply("唔……只差一點點就能拿到 Full Combo 了呢！別氣餒，喝杯蔥茶休息一下，Miku 會一直用歌聲為你注入滿滿能量的！(MIKU POWER 充電中🔋✨) 下次一定可以的，加油啾咪♪")

        # ✨ 情況 C：Miss 數在 5 到 10 之間
        elif 5 <= miss_count <= 10:
            try:
                # 提示：'👍🏻' 包含膚色特徵，在 Discord 程式碼中可以安全使用
                await fetched_message.add_reaction('👍🏻')
            except Exception as e:
                print(f"無法添加 👍🏻 反應: {e}")
            await fetched_message.reply("主唱大人快看過來～！Miku 發現這次一定是舞台地板太滑了啦！先甩甩手指、放鬆一下肩膀吧♪ 只要不放棄練習，你的節奏感一定會像旋律一樣越來越完美的，我們再一起挑戰下一首曲子吧！💚")
            
        else:
            # 如果 Miss 數剛好是 4，或是大於 10，就只會有最前面的 🔥 反應，不做其他回覆
            print(f"[osu! 互動] 玩家 Miss 數為 {miss_count}，不符合額外應援區間。")