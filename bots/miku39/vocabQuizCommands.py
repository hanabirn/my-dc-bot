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


# 記錄每個使用者「目前正在進行的測驗」進度：author_id -> session dict。
# 一次只能有一場測驗在跑（避免同一人在多個頻道各開一場，狀態互相打架）；
# session 是同一份 dict 物件在整場測驗的所有 View 之間傳來傳去，被
# /停止單字測驗 或按鈕點掉之後就從這裡移除，View 靠「這個 session 是否還
# 掛在這裡」來判斷自己是不是已經是一場「已經結束的舊測驗」的殘留畫面。
_ACTIVE_SESSIONS = {}


def _session_summary(session, title):
    return discord.Embed(
        title=title,
        description=f"共作答 {session['done']}/{session['total']} 題，答對 **{session['correct']}** 題。",
        color=discord.Color.from_str("#39C5BB"),
    )


def _make_question_embed(session):
    word_entry = session["word_entry"]
    embed = discord.Embed(
        title=f"📖 JLPT {session['level']} 漢字讀音測驗　第 {session['done'] + 1}/{session['total']} 題",
        description=f"# {word_entry['word']}\n\n這個漢字怎麼唸？",
        color=discord.Color.from_str("#39C5BB"),
    )
    embed.set_footer(text="30 秒內點選按鈕作答")
    return embed


class VocabQuizView(discord.ui.View):
    def __init__(self, author_id, session, pool):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.session = session
        self.pool = pool
        self.answered = False
        self.message = None

        for opt in session["options"]:
            self.add_item(self._make_answer_button(opt))
        self.add_item(self._make_stop_button())

    def _is_stale(self):
        return _ACTIVE_SESSIONS.get(self.author_id) is not self.session

    def _make_answer_button(self, option_text):
        word_entry = self.session["word_entry"]
        is_correct = option_text == word_entry["kana"]
        btn = discord.ui.Button(label=option_text, style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ 這不是你的題目，不能幫忙作答唷！", ephemeral=True)
                return
            if self.answered:
                return
            if self._is_stale():
                await interaction.response.send_message("這場測驗已經結束囉，打 /日文單字測驗 開新的一場吧！", ephemeral=True)
                return
            self.answered = True

            for child in self.children:
                child.disabled = True
                if isinstance(child, discord.ui.Button) and child.label == word_entry["kana"]:
                    child.style = discord.ButtonStyle.success
                elif child is btn and not is_correct:
                    child.style = discord.ButtonStyle.danger

            self.session["done"] += 1
            if is_correct:
                self.session["correct"] += 1

            result_text = "✅ 答對了！" if is_correct else "❌ 答錯了～"
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green() if is_correct else discord.Color.red()
            embed.add_field(
                name=result_text,
                value=f"正確讀音：**{word_entry['kana']}**\n意思：{word_entry['meaning']}",
                inline=False,
            )
            self.stop()

            if self.session["done"] >= self.session["total"]:
                _ACTIVE_SESSIONS.pop(self.author_id, None)
                await interaction.response.edit_message(embed=embed, view=None)
                await interaction.followup.send(embed=_session_summary(self.session, "🏁 測驗結束！"))
            else:
                next_view = NextQuestionView(self.author_id, self.session, self.pool)
                await interaction.response.edit_message(embed=embed, view=next_view)
                next_view.message = interaction.message

        btn.callback = callback
        return btn

    def _make_stop_button(self):
        btn = discord.ui.Button(label="🛑 結束測驗", style=discord.ButtonStyle.danger, row=1)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ 這不是你的測驗，不能幫忙結束唷！", ephemeral=True)
                return
            if self.answered:
                return
            self.answered = True
            _ACTIVE_SESSIONS.pop(self.author_id, None)
            for child in self.children:
                child.disabled = True
            self.stop()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=_session_summary(self.session, "🛑 測驗已結束"))

        btn.callback = callback
        return btn

    async def on_timeout(self):
        if self.answered or self._is_stale():
            return
        _ACTIVE_SESSIONS.pop(self.author_id, None)
        word_entry = self.session["word_entry"]
        for child in self.children:
            child.disabled = True
            if isinstance(child, discord.ui.Button) and child.label == word_entry["kana"]:
                child.style = discord.ButtonStyle.success
        if self.message:
            embed = self.message.embeds[0]
            embed.add_field(
                name="⌛ 時間到！測驗已自動結束",
                value=f"正確讀音：**{word_entry['kana']}**\n意思：{word_entry['meaning']}",
                inline=False,
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class NextQuestionView(discord.ui.View):
    def __init__(self, author_id, session, pool):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.session = session
        self.pool = pool
        self.acted = False
        self.message = None

        self.add_item(self._make_next_button())
        self.add_item(self._make_stop_button())

    def _is_stale(self):
        return _ACTIVE_SESSIONS.get(self.author_id) is not self.session

    def _make_next_button(self):
        btn = discord.ui.Button(label="➡️ 下一題", style=discord.ButtonStyle.primary)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ 這不是你的測驗唷！", ephemeral=True)
                return
            if self.acted:
                return
            if self._is_stale():
                await interaction.response.send_message("這場測驗已經結束囉，打 /日文單字測驗 開新的一場吧！", ephemeral=True)
                return
            self.acted = True
            self.stop()

            word_entry = random.choice(self.pool)
            self.session["word_entry"] = word_entry
            self.session["options"] = _build_options(word_entry, self.pool)

            quiz_view = VocabQuizView(self.author_id, self.session, self.pool)
            await interaction.response.edit_message(embed=_make_question_embed(self.session), view=quiz_view)
            quiz_view.message = interaction.message

        btn.callback = callback
        return btn

    def _make_stop_button(self):
        btn = discord.ui.Button(label="🛑 結束測驗", style=discord.ButtonStyle.danger)

        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ 這不是你的測驗唷！", ephemeral=True)
                return
            if self.acted:
                return
            self.acted = True
            _ACTIVE_SESSIONS.pop(self.author_id, None)
            for child in self.children:
                child.disabled = True
            self.stop()
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=_session_summary(self.session, "🛑 測驗已結束"))

        btn.callback = callback
        return btn

    async def on_timeout(self):
        if self.acted or self._is_stale():
            return
        _ACTIVE_SESSIONS.pop(self.author_id, None)
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


def register_vocab_commands(bot):
    @bot.hybrid_command(name="日文單字測驗", description="JLPT 漢字讀音選擇題，可指定等級與題數")
    async def vocab_quiz_command(
        ctx,
        level: Literal["N5", "N4", "N3", "N2", "N1"] = "N5",
        count: discord.app_commands.Range[int, 1, 20] = 5,
    ):
        if ctx.author.id in _ACTIVE_SESSIONS:
            await ctx.send("你已經有一場測驗正在進行囉，先作答或打 /停止單字測驗 結束它吧！")
            return

        try:
            pool = _fetch_reading_pool(level)
        except requests.RequestException:
            await ctx.send("⚠️ 題庫讀取失敗，等一下再試試看～")
            return

        if len(pool) < 4:
            await ctx.send(f"⚠️ {level} 題庫目前題目太少，換個等級試試？")
            return

        word_entry = random.choice(pool)
        session = {
            "level": level,
            "total": count,
            "done": 0,
            "correct": 0,
            "word_entry": word_entry,
            "options": _build_options(word_entry, pool),
        }
        _ACTIVE_SESSIONS[ctx.author.id] = session

        view = VocabQuizView(ctx.author.id, session, pool)
        message = await ctx.send(embed=_make_question_embed(session), view=view)
        view.message = message

    @bot.hybrid_command(name="停止單字測驗", description="結束你正在進行的日文單字測驗")
    async def stop_vocab_quiz_command(ctx):
        session = _ACTIVE_SESSIONS.pop(ctx.author.id, None)
        if not session:
            await ctx.send("你目前沒有進行中的單字測驗～")
            return
        await ctx.send(embed=_session_summary(session, "🛑 測驗已結束"))
