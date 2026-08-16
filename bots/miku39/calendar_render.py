# calendar_render.py
# 把 /簽到 的紀錄畫成一張卡通風格的月曆圖：圓角白卡、蔥綠(#39C5BB)＋螢光粉紅
# (#FF007F)＋深灰／白的 Miku 主題配色，已簽到的日期會蓋上一張真的初音未來Q版
# 貼圖印章（bots/miku39/assets/miku_stamp.png，去背自使用者提供的貼圖圖片；如果
# 之後放了同資料夾的其他貼圖如 negi.png，會混在一起隨機抽一張貼，增加變化）。
# 星期標題故意用英文縮寫（Sun/Mon/...），標題旁的音符裝飾、今天的「01」徽章、
# 卡片四角的科技感邊框都全部用 PIL 圖形基本元素（橢圓/線段/多邊形）畫出來，不用
# 文字符號——是因為 PIL 內建字型（load_default）不支援中文字或 ♪☆ 這類符號，會
# 直接顯示空白方塊。Pillow 10.1+ 的 load_default(size=...) 可以縮放內建字型且維持
# 清晰，搭配 stroke_width 疊一圈描邊模擬粗體，標題/日期數字才有卡通貼圖那種厚實感。
#
# 背景圖片：優先讀 bots/miku39/assets/bg.png（等比例裁滿整個畫布＋疊一層半透明白
# 遮罩，確保格線跟數字仍然清晰），這個檔案不存在就自動退回目前的薄荷藍→粉漸層。
# 想換 Miku 背景圖的話，直接把圖片存成那個檔名即可，不用改程式碼。
import calendar as cal_module
import math
import os
import random
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

MIKU_TEAL = (57, 197, 187)        # 蔥綠 #39C5BB，Miku 招牌色
MIKU_TEAL_GLOW = (13, 214, 191)   # 加亮蔥綠，已簽到格子的邊框用
NEON_PINK = (255, 0, 127)         # 螢光粉紅 #FF007F，今天／週末的點綴色
INK = (36, 40, 44)                # 深灰／黑，平日標籤跟科技感邊框用
CARD_COLOR = (255, 255, 255)
CELL_COLOR = (247, 248, 249)
CELL_CHECKED_COLOR = (223, 250, 246)
GRID_COLOR = (222, 225, 227)
TEXT_COLOR = (36, 40, 44)
MUTED_TEXT = (150, 155, 158)
STAR_COLOR = (255, 200, 87)
HEADER_BAND = MIKU_TEAL
HEADER_TEXT = (255, 255, 255)
WEEKEND_PILL = NEON_PINK
WEEKDAY_PILL = INK
PILL_TEXT = (255, 255, 255)
SKIN_COLOR = (255, 232, 214)
BLUSH_COLOR = (255, 173, 190)
FACE_LINE = (110, 90, 70)
GRADIENT_FROM = (214, 245, 240)   # 沒有 bg.png 時的備援漸層：薄荷藍
GRADIENT_TO = (255, 232, 240)     # → 淡粉，左到右淡淡過渡

WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

CELL_W = 64
CELL_H = 60
HEADER_H = 50
WEEKDAY_H = 30
OUTER_PAD = 36  # 卡片外面留出來給背景（圖片或漸層）露臉的邊框寬度，也是「01」浮水印能露出的空間
MARGIN = OUTER_PAD + 10  # 內容跟卡片邊緣之間的留白（卡片本身從 OUTER_PAD 開始畫）
RADIUS = 12

_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_BG_IMAGE_PATH = os.path.join(_ASSET_DIR, "bg.png")

# 貼圖池：目前只有使用者提供的 miku_stamp.png，但如果之後把蔥造型貼圖存成
# negi.png 丟進同一個資料夾，會自動一起加入輪抽名單，不用改程式碼。找不到就
# 從清單裡跳過，貼圖池至少會保留原本的 miku_stamp.png（本來就在 repo 裡）。
_STICKER_CANDIDATES = ["miku_stamp.png", "negi.png"]
_STICKER_IMAGES = []
for _name in _STICKER_CANDIDATES:
    _path = os.path.join(_ASSET_DIR, _name)
    if os.path.exists(_path):
        try:
            _STICKER_IMAGES.append(Image.open(_path).convert("RGBA"))
        except Exception as e:
            print(f"[MIKU39] 讀取貼圖素材 {_name} 失敗: {e}")


def _font(size):
    return ImageFont.load_default(size=size)


def _draw_star(draw, cx, cy, r_outer, r_inner, fill, points=5):
    verts = []
    for i in range(points * 2):
        r = r_outer if i % 2 == 0 else r_inner
        angle = math.pi / points * i - math.pi / 2
        verts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(verts, fill=fill)


def _draw_note(draw, cx, cy, size, fill):
    """畫一個簡化的八分音符（實心橢圓符頭+符桿+小旗），純向量圖形，用來在標題
    旁邊加一點「這是音樂系 bot」的視覺提示，不依賴任何字型符號。"""
    head_w, head_h = size * 0.9, size * 0.68
    draw.ellipse([cx - head_w / 2, cy - head_h / 2, cx + head_w / 2, cy + head_h / 2], fill=fill)
    stem_x = cx + head_w / 2 - size * 0.08
    stem_top = cy - size * 2.1
    draw.line([(stem_x, cy), (stem_x, stem_top)], fill=fill, width=max(1, round(size * 0.16)))
    draw.polygon([
        (stem_x, stem_top),
        (stem_x + size * 0.75, stem_top + size * 0.35),
        (stem_x, stem_top + size * 0.9),
    ], fill=fill)


def _draw_corner_brackets(draw, x0, y0, x1, y1, length=16, color=INK, width=2):
    """卡片四個角落各畫一個 L 形括號，做出一點「科技感邊框」的 HUD 感，純線條、
    不影響卡片內容的可讀性。"""
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        draw.line([(cx, cy), (cx + dx * length, cy)], fill=color, width=width)
        draw.line([(cx, cy), (cx, cy + dy * length)], fill=color, width=width)


def _draw_miku_stamp_vector(draw, cx, cy, r):
    """向量版Q版初音未來小貼圖（貼圖素材讀取失敗時的備援）：雙馬尾+圓臉+瞇瞇笑
    眼+腮紅，尺寸抓 stamp 半徑 r 的比例去算，改 r 不用重新調整每個部件的位置。"""
    tail_w = r * 0.42
    draw.ellipse([cx - r * 1.15 - tail_w / 2, cy - r * 0.55, cx - r * 1.15 + tail_w / 2, cy + r * 0.95],
                 fill=MIKU_TEAL)
    draw.ellipse([cx + r * 1.15 - tail_w / 2, cy - r * 0.55, cx + r * 1.15 + tail_w / 2, cy + r * 0.95],
                 fill=MIKU_TEAL)

    draw.ellipse([cx - r * 0.92, cy - r * 0.95, cx + r * 0.92, cy + r * 0.5], fill=MIKU_TEAL)

    face_r = r * 0.72
    draw.ellipse([cx - face_r, cy - face_r * 0.78, cx + face_r, cy + face_r * 1.05], fill=SKIN_COLOR)

    for dx in (-0.42, -0.1, 0.22, 0.5):
        bx = cx + r * dx
        by = cy - face_r * 0.78 + r * 0.06
        draw.polygon([(bx - r * 0.14, by), (bx + r * 0.14, by), (bx, by + r * 0.32)], fill=MIKU_TEAL)

    blush_r = r * 0.13
    draw.ellipse([cx - face_r * 0.72 - blush_r, cy + r * 0.12 - blush_r,
                  cx - face_r * 0.72 + blush_r, cy + r * 0.12 + blush_r], fill=BLUSH_COLOR)
    draw.ellipse([cx + face_r * 0.72 - blush_r, cy + r * 0.12 - blush_r,
                  cx + face_r * 0.72 + blush_r, cy + r * 0.12 + blush_r], fill=BLUSH_COLOR)

    eye_w = r * 0.22
    eye_y = cy - r * 0.02
    lw = max(1, round(r * 0.09))
    for ex in (cx - face_r * 0.4, cx + face_r * 0.4):
        draw.line([(ex - eye_w / 2, eye_y + r * 0.1), (ex, eye_y - r * 0.08)], fill=FACE_LINE, width=lw)
        draw.line([(ex, eye_y - r * 0.08), (ex + eye_w / 2, eye_y + r * 0.1)], fill=FACE_LINE, width=lw)

    mouth_w = r * 0.34
    mouth_y = cy + r * 0.32
    draw.arc([cx - mouth_w / 2, mouth_y - r * 0.16, cx + mouth_w / 2, mouth_y + r * 0.22],
              start=20, end=160, fill=FACE_LINE, width=max(1, round(r * 0.08)))


def _load_bg_image(w, h):
    """試著讀 assets/bg.png 當背景（等比例裁滿整個畫布，cover 模式），疊一層半
    透明白色遮罩讓卡片外圍的文字/裝飾仍然清晰。檔案不存在或讀取失敗就回傳
    None，呼叫端會自動改用漸層背景頂替。"""
    if not os.path.exists(_BG_IMAGE_PATH):
        return None
    try:
        bg = Image.open(_BG_IMAGE_PATH).convert("RGB")
        scale = max(w / bg.width, h / bg.height)
        bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
        left, top = (bg.width - w) // 2, (bg.height - h) // 2
        bg = bg.crop((left, top, left + w, top + h))
        overlay = Image.new("RGB", (w, h), (255, 255, 255))
        return Image.blend(bg, overlay, alpha=0.55)
    except Exception as e:
        print(f"[MIKU39] 讀取行事曆背景圖 bg.png 失敗，改用預設漸層: {e}")
        return None


def _draw_watermark(bg, w, h):
    """卡片右下角露出一小角的「01」浮水印（Miku 經典的編號識別）。浮水印的中心
    對齊卡片右下角那個點，所以固定會有一半疊在卡片下面（被蓋住）、一半落在卡片
    外的背景邊框上（露出來），走的是海報角落浮水印的感覺，不會搶版面。"""
    wm_w, wm_h = 140, 80
    wm = Image.new("RGBA", (wm_w, wm_h), (0, 0, 0, 0))
    wdraw = ImageDraw.Draw(wm)
    wdraw.text((wm_w / 2, wm_h / 2), "01", font=_font(56), fill=(255, 255, 255, 210), anchor="mm")
    corner_x, corner_y = w - OUTER_PAD, h - OUTER_PAD
    bg.paste(wm, (corner_x - wm_w // 2, corner_y - wm_h // 2), wm)


def _build_background(w, h):
    """畫布最底層：優先用 assets/bg.png（有的話），否則用薄荷藍→淡粉的漸層，
    再疊一層柔化過的陰影，讓白色卡片有種輕輕浮起來的立體感，右下角再露一小角
    「01」浮水印。"""
    bg = _load_bg_image(w, h)
    if bg is None:
        grad = Image.linear_gradient("L").transpose(Image.ROTATE_90).resize((w, h))
        bg = ImageOps.colorize(grad, black=GRADIENT_FROM, white=GRADIENT_TO)
    bg = bg.convert("RGBA")

    _draw_watermark(bg, w, h)

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [OUTER_PAD + 3, OUTER_PAD + 5, w - OUTER_PAD + 3, h - OUTER_PAD + 5],
        radius=RADIUS + 4, fill=(20, 30, 30, 80)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    bg = Image.alpha_composite(bg, shadow)

    ddraw = ImageDraw.Draw(bg)
    for sx, sy, sr, sfill in (
        (26, h - 22, 4, (255, 255, 255, 130)),
        (w - 30, 24, 3, (255, 255, 255, 120)),
    ):
        _draw_star(ddraw, sx, sy, r_outer=sr, r_inner=sr * 0.42, fill=sfill)

    return bg.convert("RGB")


def _stamp_checkin_cell(img, draw, cx, cy, r):
    """已簽到格子的印章：從貼圖池隨機挑一張真的 Miku 貼圖素材貼上去；貼圖池是
    空的（素材完全讀取失敗）才退回向量畫的版本，行事曆本身不會壞掉。"""
    if _STICKER_IMAGES:
        sticker = random.choice(_STICKER_IMAGES)
        target_h = round(r * 2.05)
        scale = target_h / sticker.height
        target_w = round(sticker.width * scale)
        resized = sticker.resize((target_w, target_h), Image.LANCZOS)
        img.paste(resized, (round(cx - target_w / 2), round(cy - target_h / 2)), resized)
    else:
        _draw_miku_stamp_vector(draw, cx, cy, r)


def render_checkin_calendar(year: int, month: int, checked_dates: set, today_str: str) -> BytesIO:
    """畫出 year/month 那個月的簽到行事曆（Miku 主題卡通風格）。checked_dates 是
    'YYYY-MM-DD' 字串的集合，today_str 是今天的日期字串。回傳可直接當
    discord.File 附件送出的 PNG bytes（呼叫端記得 seek(0) 已經處理好，直接用就好）。"""
    cal_module.setfirstweekday(cal_module.SUNDAY)
    weeks = cal_module.monthcalendar(year, month)

    width = MARGIN * 2 + CELL_W * 7
    height = MARGIN * 2 + HEADER_H + WEEKDAY_H + CELL_H * len(weeks)

    img = _build_background(width, height)
    draw = ImageDraw.Draw(img)

    # 卡片底：整個行事曆畫在一張圓角白卡上，跟背景拉開層次；四個角落加科技感括號
    card_box = [OUTER_PAD, OUTER_PAD, width - OUTER_PAD, height - OUTER_PAD]
    draw.rounded_rectangle(card_box, radius=RADIUS + 4, fill=CARD_COLOR)
    _draw_corner_brackets(draw, *card_box, length=16, color=INK, width=2)

    # 標題橫幅（蔥綠實色，白字，兩側各點綴一個音符）
    title_font = _font(18)
    draw.rounded_rectangle([MARGIN, MARGIN, width - MARGIN, MARGIN + HEADER_H - 8],
                            radius=RADIUS, fill=HEADER_BAND)
    title = f"{year}.{month:02d} Check-in Calendar"
    title_cy = MARGIN + (HEADER_H - 8) / 2
    draw.text((width / 2, title_cy), title, fill=HEADER_TEXT, font=title_font, anchor="mm", stroke_width=1, stroke_fill=HEADER_TEXT)
    _draw_note(draw, MARGIN + 22, title_cy + 3, 7, HEADER_TEXT)
    _draw_note(draw, width - MARGIN - 22, title_cy + 3, 7, HEADER_TEXT)

    # 星期標題：平日深灰底、週末螢光粉紅底，白字
    weekday_font = _font(13)
    grid_top = MARGIN + HEADER_H
    for i, label in enumerate(WEEKDAY_LABELS):
        x0 = MARGIN + i * CELL_W + 4
        x1 = MARGIN + (i + 1) * CELL_W - 4
        pill_color = WEEKEND_PILL if i in (0, 6) else WEEKDAY_PILL
        draw.rounded_rectangle([x0, grid_top + 2, x1, grid_top + WEEKDAY_H - 2], radius=9, fill=pill_color)
        cx = MARGIN + i * CELL_W + CELL_W / 2
        draw.text((cx, grid_top + WEEKDAY_H / 2), label, fill=PILL_TEXT, font=weekday_font, anchor="mm")

    grid_top += WEEKDAY_H
    day_font = _font(13)
    badge_font = _font(10)
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x0 = MARGIN + c * CELL_W + 3
            y0 = grid_top + r * CELL_H + 3
            x1 = MARGIN + (c + 1) * CELL_W - 3
            y1 = grid_top + (r + 1) * CELL_H - 3
            if day == 0:
                continue

            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            checked = date_str in checked_dates
            is_today = date_str == today_str

            cell_fill = CELL_CHECKED_COLOR if checked else CELL_COLOR
            if is_today:
                border_color, border_w = NEON_PINK, 3
            elif checked:
                border_color, border_w = MIKU_TEAL_GLOW, 3
            else:
                border_color, border_w = GRID_COLOR, 1
            draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS, fill=cell_fill, outline=border_color, width=border_w)

            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

            if checked:
                stamp_r = min(CELL_W, CELL_H) / 2 - 8
                _stamp_checkin_cell(img, draw, cx, cy + 2, stamp_r)
                draw.text((x1 - 6, y0 + 5), str(day), fill=MUTED_TEXT, font=day_font, anchor="ra")
            else:
                draw.text((x0 + 8, y0 + 6), str(day), fill=TEXT_COLOR, font=day_font, anchor="la")

            if is_today:
                # 「今天」不再用星星標記，改用 Miku 招牌的「01」編號徽章，跟浮水印
                # 呼應同一個視覺語彙
                badge_r = 11
                bcx, bcy = x1 - badge_r - 2, y0 + badge_r + 2
                draw.ellipse([bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r], fill=NEON_PINK)
                draw.text((bcx, bcy), "01", fill=(255, 255, 255), font=badge_font, anchor="mm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_checkin_calendar(user_id, checked_days, year=None, month=None) -> BytesIO:
    """跟 render_checkin_calendar 共用同一份繪圖邏輯的簡化介面：checked_days 是
    這個月已簽到的「日期數字」列表（例如 [1, 5, 16]），year/month 預設為目前 UTC
    月份。user_id 目前沒有拿來改變畫面（行事曆本身不分使用者風格），保留參數只是
    為了跟外部呼叫端的介面對齊，不會影響繪圖結果。"""
    now = datetime.now(timezone.utc)
    year = year or now.year
    month = month or now.month
    checked_dates = {f"{year:04d}-{month:02d}-{int(d):02d}" for d in checked_days}
    today_str = now.strftime("%Y-%m-%d")
    return render_checkin_calendar(year, month, checked_dates, today_str)
