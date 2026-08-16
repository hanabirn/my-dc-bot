"""多語言單字測驗——從「我的網站」的 js/quiz.js 移植過來的出題邏輯：
JLPT 各級 Google Sheet 是同一份共用試算表格式（word,kana,meaning,english）。單字依
「是否含漢字」分成兩個題庫、各自考不同題型（跟網站版 addWord() 的池子分流規則一致）：
  - 含漢字的單字（含漢字+假名混合，例如「話す」）→ 讀音題，錯誤選項用 mutate_kana()
    對正確讀音做小幅變形（濁音切換、插入/刪除一個假名、相鄰互換），而不是隨機抓別的
    單字讀音，出題風格才會貼近真正的 JLPT 讀音選擇題。
  - 不含漢字的純假名單字（平假名或片假名，例如「スポーツ」）→ 意思題，因為這種字本身
    就是讀音了，沒有讀音好考，錯誤選項改成隨機抓題庫裡其他單字的中文意思。

韓文/法文/英文沒有漢字讀音這種東西可以考，全部都是意思題，題庫來自跟網站版
js/quiz.js 的 SHEETS.kr / SHEETS.fr / SHEETS.en 同一份 Google Sheet——這幾份表格
是給人閱讀用的「一列印好幾組單字」排版（每組是 word/中文意思/英文 的一個區塊，
橫向重複好幾組），欄位起始位置跟網站版的 parseKorean/parseFrench/parseEnglish
一致，只是這裡用 Python 重新實作一次同樣的欄位規則。

TOPIK（韓文檢定）分級題庫則跟 JLPT 一樣是「一列一個單字」的乾淨格式
（word,meaning,english），跟網站版的 TOPIK_SHEETS/parseTopikVocab 對應——但
韓文本身就是表音文字，沒有漢字讀音好考，所以固定都是意思題。
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

FLAT_SHEETS = {
    "kr": "https://docs.google.com/spreadsheets/d/1BsO7tpzFgO39AyBo2SV1RZFDWfPECB-LzWBGA87nbQA/export?format=csv&gid=0",
    "fr": "https://docs.google.com/spreadsheets/d/1Ki0fuTZb1netmpSOBd8uJbZnYhgtD17aEtGQb3Ehb3Y/export?format=csv&gid=0",
    "en": "https://docs.google.com/spreadsheets/d/1Uof80EqNrC3SrtAcce0OgQDr_MRpqcxCQCb2oQS4I0s/export?format=csv&gid=0",
}

# TOPIK_SHEETS 的 key 是純等級數字（"1".."4"），跟網站版 TOPIK_SHEETS 的
# topik_1..topik_4 對應；統一的 quiz key 命名空間裡則用 "TOPIK1".."TOPIK4"
# 前綴版本，避免跟其他語言的 key 混淆（見 _fetch_vocab_pools/_quiz_label）。
TOPIK_SHEETS = {
    "1": "https://docs.google.com/spreadsheets/d/1XJTpFBly3hRNBBBnZoAzJneOXwJajbC4KqniSRfSPUg/export?format=csv&gid=0",
    "2": "https://docs.google.com/spreadsheets/d/1FBjH5ObsgShVevgMcXXJDmsmh0JQBzk6DDsJAyi6kaE/export?format=csv&gid=0",
    "3": "https://docs.google.com/spreadsheets/d/1pVOTCK3e2OgAhdktgVb29j4vUlKpmIULk2OnkiPeNA0/export?format=csv&gid=0",
    "4": "https://docs.google.com/spreadsheets/d/1UZJ29Jxl8pjM4eZREWKed8YRkPpjRIKkSfzfYFaAlig/export?format=csv&gid=0",
}

_QUIZ_LABELS = {"kr": "韓文", "fr": "法文", "en": "英文"}

# {key: (fetched_at_epoch_seconds, (reading_pool, meaning_pool))} — each pool is a
# list of {"word":..., "kana":..., "meaning":..., "english":...}. key is a JLPT
# level ("N5".."N1"), a TOPIK level ("TOPIK1".."TOPIK4"), or a flat-language
# code ("kr"/"fr"/"en").
_VOCAB_CACHE = {}
_CACHE_TTL_SECONDS = 3600


def _has_kanji(s):
    return any(0x4E00 <= ord(c) <= 0x9FAF for c in s)


def _is_valid_word(word, meaning):
    """網站版 isValidWord() 的 Python 版本——濾掉表頭文字外洩到資料列的髒資料
    （像「單字」「意思」「Video」這些欄位標題字樣，或是純數字的列編號）。"""
    if not word or not meaning:
        return False
    junk_in_word = ("動畫", "動画", "동영상", "註", "★", "單字")
    junk_in_meaning = ("動畫", "動画", "意思", "註")
    if any(j in word for j in junk_in_word):
        return False
    if any(j in meaning for j in junk_in_meaning):
        return False
    if word.isdigit():
        return False
    return True


def _download_csv_rows(url):
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    # Google's CSV export doesn't send a charset in Content-Type, so requests
    # falls back to guessing (often wrong) instead of reading it as UTF-8.
    reader = csv.reader(io.StringIO(resp.content.decode("utf-8")))
    return list(reader)


def _parse_jlpt_pools(rows):
    reading_pool = []
    meaning_pool = []
    for row in rows[1:]:  # 第一列是表頭：word,kana,meaning,english
        if len(row) < 4:
            continue
        word, kana, meaning, english = row[0].strip(), row[1].strip(), row[2].strip(), row[3].strip()
        if not _is_valid_word(word, meaning):
            continue
        entry = {"word": word, "kana": kana, "meaning": meaning, "english": english}
        if _has_kanji(word):
            if kana:
                reading_pool.append(entry)
        else:
            meaning_pool.append(entry)
    return reading_pool, meaning_pool


def _parse_stride5_meaning_pool(rows):
    """韓文/法文表格排版：每列橫向排 4 組「編號,單字,中文意思,英文,(空白)」，
    組與組之間欄位間隔 5（起始欄位 2,7,12,17），跟網站版 parseKorean/
    parseFrench 讀到的組數一致（表格裡其實留了第 5 組的欄位，但那組實際上是
    空的，網站版本來就沒讀它，這裡也不用特別處理）。"""
    pool = []
    for row in rows:
        for offset in (2, 7, 12, 17):
            if offset + 1 >= len(row):
                continue
            word = row[offset].strip()
            meaning = row[offset + 1].strip()
            english = row[offset + 2].strip() if offset + 2 < len(row) else ""
            if not _is_valid_word(word, meaning):
                continue
            pool.append({"word": word, "kana": "", "meaning": meaning, "english": english})
    return pool


def _parse_english_meaning_pool(rows):
    """英文表格排版：每列橫向排 5 組「編號,單字,中文意思,Video,(空白)」，組與
    組之間欄位間隔 4（起始欄位 2,6,10,14,18），跟網站版 parseEnglish 一致。"""
    pool = []
    for row in rows:
        for offset in (2, 6, 10, 14, 18):
            if offset + 1 >= len(row):
                continue
            word = row[offset].strip()
            meaning = row[offset + 1].strip()
            if not _is_valid_word(word, meaning):
                continue
            pool.append({"word": word, "kana": "", "meaning": meaning, "english": ""})
    return pool


def _parse_topik_pool(rows):
    """TOPIK 表格排版：跟 JLPT 一樣一列一個單字，只是沒有讀音欄——
    word,meaning,english（跟網站版 parseTopikVocab 一致）。"""
    pool = []
    for row in rows[1:]:  # 第一列是表頭：韓文單字,繁體中文翻譯,English
        if len(row) < 3:
            continue
        word, meaning, english = row[0].strip(), row[1].strip(), row[2].strip()
        if not _is_valid_word(word, meaning):
            continue
        pool.append({"word": word, "kana": "", "meaning": meaning, "english": english})
    return pool


def _fetch_vocab_pools(key):
    """回傳 (reading_pool, meaning_pool)。JLPT 等級才有 reading_pool（含漢字、拿
    來出讀音題的單字），其他語言（韓文/法文/英文/TOPIK）的 reading_pool 永遠是
    空的——全部都出意思題。"""
    cached = _VOCAB_CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    if key in JLPT_SHEETS:
        rows = _download_csv_rows(JLPT_SHEETS[key])
        pools = _parse_jlpt_pools(rows)
    elif key in ("kr", "fr"):
        rows = _download_csv_rows(FLAT_SHEETS[key])
        pools = ([], _parse_stride5_meaning_pool(rows))
    elif key == "en":
        rows = _download_csv_rows(FLAT_SHEETS[key])
        pools = ([], _parse_english_meaning_pool(rows))
    elif key.startswith("TOPIK") and key[5:] in TOPIK_SHEETS:
        rows = _download_csv_rows(TOPIK_SHEETS[key[5:]])
        pools = ([], _parse_topik_pool(rows))
    else:
        raise ValueError(f"unknown quiz key: {key}")

    if pools[0] or pools[1]:
        _VOCAB_CACHE[key] = (time.time(), pools)
    return pools


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


def _build_reading_options(word_entry, pool):
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


def _build_meaning_options(word_entry, pool):
    """意思題沒有「近似變形」這種東西可用，錯誤選項就跟網站版一樣直接從題庫
    隨機抓別的單字意思來湊。"""
    options = [word_entry["meaning"]]
    guard = 0
    while len(options) < 4 and guard < 200:
        guard += 1
        pick = random.choice(pool)["meaning"]
        if pick not in options:
            options.append(pick)
    random.shuffle(options)
    return options


def _pick_question(key):
    """回傳 (qtype, word_entry, options)，qtype 是 'reading' 或 'meaning'；
    兩個題庫都不夠出題時回傳 None。哪個題庫可以出題就出那種題型，兩個都夠的話
    隨機選一種——跟網站版 pickQuestionType() 的 50/50 邏輯一致。"""
    reading_pool, meaning_pool = _fetch_vocab_pools(key)
    can_reading = len(reading_pool) >= 4
    can_meaning = len(meaning_pool) >= 4
    if not can_reading and not can_meaning:
        return None

    if can_reading and can_meaning:
        qtype = random.choice(["reading", "meaning"])
    else:
        qtype = "reading" if can_reading else "meaning"

    if qtype == "reading":
        word_entry = random.choice(reading_pool)
        options = _build_reading_options(word_entry, reading_pool)
    else:
        word_entry = random.choice(meaning_pool)
        options = _build_meaning_options(word_entry, meaning_pool)
    return qtype, word_entry, options


def _correct_answer(session):
    word_entry = session["word_entry"]
    return word_entry["kana"] if session["qtype"] == "reading" else word_entry["meaning"]


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


def _truncate_label(text, limit=80):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _quiz_label(key):
    if key in JLPT_SHEETS:
        return f"JLPT {key}"
    if key.startswith("TOPIK"):
        return f"TOPIK {key[5:]}"
    return _QUIZ_LABELS[key]


def _make_question_embed(session):
    word_entry = session["word_entry"]
    qtype = session["qtype"]
    progress = f"第 {session['done'] + 1}/{session['total']} 題"
    label = _quiz_label(session["key"])
    if qtype == "reading":
        title = f"📖 {label} 漢字讀音測驗　{progress}"
        question = "這個漢字怎麼唸？"
    else:
        title = f"📖 {label} 單字意思測驗　{progress}"
        question = "這個字是什麼意思？"
    embed = discord.Embed(
        title=title,
        description=f"# {word_entry['word']}\n\n{question}",
        color=discord.Color.from_str("#39C5BB"),
    )
    embed.set_footer(text="30 秒內點選按鈕作答")
    return embed


def _answer_reveal_field(session, is_correct):
    word_entry = session["word_entry"]
    result_text = "✅ 答對了！" if is_correct else "❌ 答錯了～"
    if session["qtype"] == "reading":
        value = f"正確讀音：**{word_entry['kana']}**\n意思：{word_entry['meaning']}"
    else:
        value = f"正確意思：**{word_entry['meaning']}**"
    return result_text, value


class VocabQuizView(discord.ui.View):
    def __init__(self, author_id, session):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.session = session
        self.answered = False
        self.message = None

        correct_answer = _correct_answer(session)
        for opt in session["options"]:
            self.add_item(self._make_answer_button(opt, opt == correct_answer))
        self.add_item(self._make_stop_button())

    def _is_stale(self):
        return _ACTIVE_SESSIONS.get(self.author_id) is not self.session

    def _make_answer_button(self, option_text, is_correct):
        btn = discord.ui.Button(label=_truncate_label(option_text), style=discord.ButtonStyle.secondary)
        btn.is_correct_answer = is_correct

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
                if isinstance(child, discord.ui.Button) and getattr(child, "is_correct_answer", False):
                    child.style = discord.ButtonStyle.success
                elif child is btn and not is_correct:
                    child.style = discord.ButtonStyle.danger

            self.session["done"] += 1
            if is_correct:
                self.session["correct"] += 1

            result_text, result_value = _answer_reveal_field(self.session, is_correct)
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.green() if is_correct else discord.Color.red()
            embed.add_field(name=result_text, value=result_value, inline=False)
            self.stop()

            if self.session["done"] >= self.session["total"]:
                _ACTIVE_SESSIONS.pop(self.author_id, None)
                await interaction.response.edit_message(embed=embed, view=None)
                await interaction.followup.send(embed=_session_summary(self.session, "🏁 測驗結束！"))
            else:
                next_view = NextQuestionView(self.author_id, self.session)
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
        for child in self.children:
            child.disabled = True
            if isinstance(child, discord.ui.Button) and getattr(child, "is_correct_answer", False):
                child.style = discord.ButtonStyle.success
        if self.message:
            _, result_value = _answer_reveal_field(self.session, is_correct=False)
            embed = self.message.embeds[0]
            embed.add_field(name="⌛ 時間到！測驗已自動結束", value=result_value, inline=False)
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class NextQuestionView(discord.ui.View):
    def __init__(self, author_id, session):
        super().__init__(timeout=30.0)
        self.author_id = author_id
        self.session = session
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

            question = _pick_question(self.session["key"])
            if question is None:
                self.acted = True
                _ACTIVE_SESSIONS.pop(self.author_id, None)
                self.stop()
                await interaction.response.edit_message(view=None)
                await interaction.followup.send("⚠️ 題庫暫時讀取失敗，測驗提前結束了，等一下再試試看～")
                return
            self.acted = True
            self.stop()

            qtype, word_entry, options = question
            self.session["qtype"] = qtype
            self.session["word_entry"] = word_entry
            self.session["options"] = options

            quiz_view = VocabQuizView(self.author_id, self.session)
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


async def _start_quiz(ctx, key, count):
    if ctx.author.id in _ACTIVE_SESSIONS:
        await ctx.send("你已經有一場測驗正在進行囉，先作答或打 /停止單字測驗 結束它吧！")
        return

    try:
        question = _pick_question(key)
    except requests.RequestException:
        await ctx.send("⚠️ 題庫讀取失敗，等一下再試試看～")
        return

    if question is None:
        await ctx.send(f"⚠️ {_quiz_label(key)}題庫目前題目太少，等一下再試試？")
        return

    qtype, word_entry, options = question
    session = {
        "key": key,
        "total": count,
        "done": 0,
        "correct": 0,
        "qtype": qtype,
        "word_entry": word_entry,
        "options": options,
    }
    _ACTIVE_SESSIONS[ctx.author.id] = session

    view = VocabQuizView(ctx.author.id, session)
    message = await ctx.send(embed=_make_question_embed(session), view=view)
    view.message = message


def register_vocab_commands(bot):
    @bot.hybrid_command(
        name="日文單字測驗",
        description="JLPT 選擇題（漢字讀音 + 假名單字意思），可指定等級與題數",
    )
    async def vocab_quiz_jp(
        ctx,
        level: Literal["N5", "N4", "N3", "N2", "N1"] = "N5",
        count: discord.app_commands.Range[int, 1, 20] = 5,
    ):
        await _start_quiz(ctx, level, count)

    @bot.hybrid_command(name="韓文單字測驗", description="韓文單字意思選擇題，可指定題數")
    async def vocab_quiz_kr(ctx, count: discord.app_commands.Range[int, 1, 20] = 5):
        await _start_quiz(ctx, "kr", count)

    @bot.hybrid_command(name="韓文檢定", description="TOPIK 韓文單字意思選擇題，可指定等級與題數")
    async def vocab_quiz_topik(
        ctx,
        level: Literal["1", "2", "3", "4"] = "1",
        count: discord.app_commands.Range[int, 1, 20] = 5,
    ):
        await _start_quiz(ctx, f"TOPIK{level}", count)

    @bot.hybrid_command(name="法文單字測驗", description="法文單字意思選擇題，可指定題數")
    async def vocab_quiz_fr(ctx, count: discord.app_commands.Range[int, 1, 20] = 5):
        await _start_quiz(ctx, "fr", count)

    @bot.hybrid_command(name="英文單字測驗", description="英文單字意思選擇題，可指定題數")
    async def vocab_quiz_en(ctx, count: discord.app_commands.Range[int, 1, 20] = 5):
        await _start_quiz(ctx, "en", count)

    @bot.hybrid_command(name="停止單字測驗", description="結束你正在進行的單字測驗")
    async def stop_vocab_quiz_command(ctx):
        session = _ACTIVE_SESSIONS.pop(ctx.author.id, None)
        if not session:
            await ctx.send("你目前沒有進行中的單字測驗～")
            return
        await ctx.send(embed=_session_summary(session, "🛑 測驗已結束"))
