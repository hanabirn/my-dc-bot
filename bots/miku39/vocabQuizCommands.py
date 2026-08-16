"""日文單字測驗（JLPT 漢字讀音選擇題）——從「我的網站」的 js/quiz.js 移植過來的
出題邏輯：JLPT 各級 Google Sheet 是同一份共用試算表格式（word,kana,meaning,english），
只挑「含漢字」的單字出讀音題，錯誤選項用 mutate_kana() 對正確讀音做小幅變形（濁音切換、
插入/刪除一個假名、相鄰互換），生成看起來很像的近似答案，而不是隨機抓別的單字讀音，
出題風格才會貼近真正的 JLPT 讀音選擇題。
"""
import csv
import io
import random
import time
from typing import Literal

import discord
import requests

JLPT_SHEETS = {
    "N5": "https://docs.google.com/spreadsheets/d/12B2ZV8eGUO7d1-YcWNLTlqDptkNrhsQvijyjed6Y_TE/export?format=csv&gid=0",
    "N4": "https://docs.google.com/spreadsheets/d/1unwngsmxA4_HoNMO9l0-mN4dkhrQF7vYbbHgdSDY4SQ/export?format=csv&gid=0",
    "N3": "https://docs.google.com/spreadsheets/d/1Tw8Ll29yjH-AkYlVWjTlWSY1Kh33Jxj_gqxWWcVs4NQ/export?format=csv&gid=0",
    "N2": "https://docs.google.com/spreadsheets/d/1GKE8uKb8mH8PSHYELErZbzrYAgU19u1eBLTJsy67S-4/export?format=csv&gid=0",
    "N1": "https://docs.google.com/spreadsheets/d/1zHezXxlkiSKsIzFCyUMBCLRNOxQV0zwvAgYnMFqnQ38/export?format=csv&gid=0",
}

# {level: (fetched_at_epoch_seconds, [{"word":..., "kana":..., "meaning":..., "english":...}, ...])}
_VOCAB_CACHE = {}
_CACHE_TTL_SECONDS = 3600


def _has_kanji(s):
    return any(0x4E00 <= ord(c) <= 0x9FAF for c in s)


def _fetch_reading_pool(level):
    cached = _VOCAB_CACHE.get(level)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    resp = requests.get(JLPT_SHEETS[level], timeout=10)
    resp.raise_for_status()
    # Google's CSV export doesn't send a charset in Content-Type, so requests
    # falls back to guessing (often wrong) instead of reading it as UTF-8.
    reader = csv.reader(io.StringIO(resp.content.decode("utf-8")))
    rows = list(reader)

    pool = []
    for row in rows[1:]:  # 第一列是表頭：word,kana,meaning,english
        if len(row) < 4:
            continue
        word, kana, meaning, english = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
        if not word or not meaning:
            continue
        # 跟網站版一致：只有「含漢字」的單字才會被拿來出讀音題（純假名單字沒有
        # 讀音好考，網站那邊是拿去考中文意思）
        if _has_kanji(word) and kana:
            pool.append({"word": word, "kana": kana, "meaning": meaning, "english": english})

    if pool:
        _VOCAB_CACHE[level] = (time.time(), pool)
    return pool


# ===== 近似讀音產生器（js/quiz.js 的 mutateKana / generateSimilarReadings 的 Python 版本）=====

_DAKUTEN_PAIRS = [
    ("か", "が"), ("き", "ぎ"), ("く", "ぐ"), ("け", "げ"), ("こ", "ご"),
    ("さ", "ざ"), ("し", "じ"), ("す", "ず"), ("せ", "ぜ"), ("そ", "ぞ"),
    ("た", "だ"), ("ち", "ぢ"), ("つ", "づ"), ("て", "で"), ("と", "ど"),
    ("は", "ば"), ("ひ", "び"), ("ふ", "ぶ"), ("へ", "べ"), ("ほ", "ぼ"),
    ("は", "ぱ"), ("ひ", "ぴ"), ("ふ", "ぷ"), ("へ", "ぺ"), ("ほ", "ぽ"),
]
_DAKUTEN_MAP = {}
for _base, _voiced in _DAKUTEN_PAIRS:
    _DAKUTEN_MAP.setdefault(_base, []).append(_voiced)
    _DAKUTEN_MAP.setdefault(_voiced, []).append(_base)

_INSERT_CHARS = list(
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんっゃゅょー"
)


def _mutate_kana(s):
    chars = list(s)
    strategies = []

    def dakuten():
        idxs = [i for i, c in enumerate(chars) if c in _DAKUTEN_MAP]
        if not idxs:
            return None
        i = random.choice(idxs)
        rep = random.choice(_DAKUTEN_MAP[chars[i]])
        return "".join(chars[:i]) + rep + "".join(chars[i + 1:])

    def insert():
        i = random.randint(0, len(chars))
        c = random.choice(_INSERT_CHARS)
        return "".join(chars[:i]) + c + "".join(chars[i:])

    strategies.append(dakuten)
    strategies.append(insert)

    if len(chars) > 1:
        def delete():
            i = random.randint(0, len(chars) - 1)
            return "".join(chars[:i]) + "".join(chars[i + 1:])

        def swap():
            i = random.randint(0, len(chars) - 2)
            a = chars[:]
            a[i], a[i + 1] = a[i + 1], a[i]
            return "".join(a)

        strategies.append(delete)
        strategies.append(swap)

    random.shuffle(strategies)
    for fn in strategies:
        res = fn()
        if res and res != s:
            return res
    return None


def generate_similar_readings(correct, count):
    results = set()
    attempts = 0
    while len(results) < count and attempts < 200:
        attempts += 1
        variant = _mutate_kana(correct)
        if variant and random.random() < 0.5:
            second = _mutate_kana(variant)
            if second:
                variant = second
        if variant and variant != correct and variant not in results:
            results.add(variant)
    return list(results)


def _build_options(word_entry, pool):
    options = [word_entry["kana"]] + generate_similar_readings(word_entry["kana"], 3)
    # 極少數超短讀音可能生不出 3 個不重複的變形，這時才 fallback 去題庫裡隨機
    # 抓別的單字讀音湊數（跟網站版行為一致）
    guard = 0
    while len(options) < 4 and guard < 200:
        guard += 1
        pick = random.choice(pool)["kana"]
        if pick not in options:
            options.append(pick)
    random.shuffle(options)
    return options


class VocabQuizView(discord.ui.View):
    def __init__(self, author_id, level, word_entry, options):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.level = level
        self.word_entry = word_entry
        self.answered = False
        self.message = None

        for opt in options:
            self.add_item(self._make_button(opt))

    def _make_button(self, option_text):
        is_correct = option_text == self.word_entry["kana"]
        btn = discord.ui.Button(label=option_text, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ 這不是你的題目，不能幫忙作答唷！", ephemeral=True)
                return
            if self.answered:
                await interaction.response.send_message("這題已經作答過囉！", ephemeral=True)
                return
            self.answered = True

            for child in self.children:
                child.disabled = True
                if child.label == self.word_entry["kana"]:
                    child.style = discord.ButtonStyle.success
                elif child is btn and not is_correct:
                    child.style = discord.ButtonStyle.danger

            result_text = "✅ 答對了！" if is_correct else "❌ 答錯了～"
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green() if is_correct else discord.Color.red()
            embed.add_field(
                name=result_text,
                value=f"正確讀音：**{self.word_entry['kana']}**\n意思：{self.word_entry['meaning']}",
                inline=False,
            )
            self.stop()
            await interaction.response.edit_message(embed=embed, view=self)

        btn.callback = callback
        return btn

    async def on_timeout(self):
        if self.answered:
            return
        for child in self.children:
            child.disabled = True
            if child.label == self.word_entry["kana"]:
                child.style = discord.ButtonStyle.success
        if self.message:
            embed = self.message.embeds[0]
            embed.add_field(
                name="⌛ 時間到！",
                value=f"正確讀音：**{self.word_entry['kana']}**\n意思：{self.word_entry['meaning']}",
                inline=False,
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


def register_vocab_commands(bot):
    @bot.hybrid_command(name="日文單字測驗", description="JLPT 漢字讀音選擇題，預設 N5，可指定 N4~N1")
    async def vocab_quiz_command(ctx, level: Literal["N5", "N4", "N3", "N2", "N1"] = "N5"):
        try:
            pool = _fetch_reading_pool(level)
        except requests.RequestException:
            await ctx.send("⚠️ 題庫讀取失敗，等一下再試試看～")
            return

        if len(pool) < 4:
            await ctx.send(f"⚠️ {level} 題庫目前題目太少，換個等級試試？")
            return

        word_entry = random.choice(pool)
        options = _build_options(word_entry, pool)

        embed = discord.Embed(
            title=f"📖 JLPT {level} 漢字讀音測驗",
            description=f"# {word_entry['word']}\n\n這個漢字怎麼唸？",
            color=discord.Color.from_str("#39C5BB"),
        )
        embed.set_footer(text="30 秒內點選按鈕作答")

        view = VocabQuizView(ctx.author.id, level, word_entry, options)
        message = await ctx.send(embed=embed, view=view)
        view.message = message
