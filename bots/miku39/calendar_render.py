# calendar_render.py
# 把 /簽到 的紀錄畫成一張卡通風格的月曆圖：圓角卡片、以 Miku 的招牌薄荷藍為主色、
# 粉色只當點綴（今天外框、週末標籤），已簽到的日期會蓋上一張真的初音未來Q版貼圖
# 印章（bots/miku39/assets/miku_stamp.png，去背自使用者提供的貼圖圖片）。星期標題
# 故意用英文縮寫（Sun/Mon/...），標題旁的音符裝飾也全部用 PIL 圖形基本元素（橢圓/
# 線段/多邊形）畫出來，不用文字符號——是因為 PIL 內建字型（load_default）不支援
# 中文字或 ♪☆ 這類符號，會直接顯示空白方塊。Pillow 10.1+ 的 load_default(size=...)
# 可以縮放內建字型且維持清晰，搭配 stroke_width 疊一圈描邊模擬粗體，標題/日期數字
# 才有卡通貼圖那種厚實感。
import calendar as cal_module
import math
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

MIKU_TEAL = (57, 197, 187)
MIKU_TEAL_DEEP = (16, 138, 128)
MIKU_TEAL_SOFT = (163, 230, 222)
BG_COLOR = (247, 253, 252)
CARD_COLOR = (255, 255, 255)
CELL_COLOR = (245, 252, 251)
CELL_CHECKED_COLOR = (223, 247, 243)
GRID_COLOR = (206, 232, 228)
TEXT_COLOR = (48, 92, 88)
MUTED_TEXT = (150, 184, 179)
TODAY_BORDER = (244, 114, 182)
STAR_COLOR = (255, 200, 87)
HEADER_BAND = (214, 245, 240)
WEEKEND_PILL = (255, 214, 231)
WEEKDAY_PILL = (185, 231, 224)
SKIN_COLOR = (255, 232, 214)
BLUSH_COLOR = (255, 173, 190)
FACE_LINE = (110, 90, 70)

WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

CELL_W = 64
CELL_H = 60
HEADER_H = 50
WEEKDAY_H = 30
MARGIN = 14
RADIUS = 12

_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_STICKER_PATH = os.path.join(_ASSET_DIR, "miku_stamp.png")

# 使用者提供的真實 Miku 貼圖，去背後快取在記憶體裡（模組只會載入一次，重複畫月曆
# 不用重複讀檔）。讀取失敗（檔案被刪、Render 部署漏帶到...）就退回 None，呼叫端
# 自動改用向量畫的Q版小圖示頂替，行事曆本身不會壞掉。
try:
    _STICKER_IMG = Image.open(_STICKER_PATH).convert("RGBA")
except Exception as e:
    print(f"[MIKU39] 讀取簽到貼圖素材失敗，將改用向量畫的Q版小圖示: {e}")
    _STICKER_IMG = None


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


def _draw_miku_stamp_vector(draw, cx, cy, r):
    """向量版Q版初音未來小貼圖（真實貼圖素材讀取失敗時的備援）：雙馬尾+圓臉+
    瞇瞇笑眼+腮紅，尺寸抓 stamp 半徑 r 的比例去算，改 r 不用重新調整每個部件的位置。"""
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


def _stamp_checkin_cell(img, draw, cx, cy, r):
    """已簽到格子的印章：優先貼真的 Miku 貼圖素材，讀取失敗才退回向量畫的版本。"""
    if _STICKER_IMG is not None:
        target_h = round(r * 2.05)
        scale = target_h / _STICKER_IMG.height
        target_w = round(_STICKER_IMG.width * scale)
        resized = _STICKER_IMG.resize((target_w, target_h), Image.LANCZOS)
        img.paste(resized, (round(cx - target_w / 2), round(cy - target_h / 2)), resized)
    else:
        _draw_miku_stamp_vector(draw, cx, cy, r)


def render_checkin_calendar(year: int, month: int, checked_dates: set, today_str: str) -> BytesIO:
    """畫出 year/month 那個月的簽到行事曆（卡通圓角風格）。checked_dates 是
    'YYYY-MM-DD' 字串的集合，today_str 是今天的日期字串。回傳可直接當
    discord.File 附件送出的 PNG bytes（呼叫端記得 seek(0) 已經處理好，直接用就好）。"""
    cal_module.setfirstweekday(cal_module.SUNDAY)
    weeks = cal_module.monthcalendar(year, month)

    width = MARGIN * 2 + CELL_W * 7
    height = MARGIN * 2 + HEADER_H + WEEKDAY_H + CELL_H * len(weeks)

    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 卡片底：整個行事曆畫在一張圓角白卡上，跟外層底色拉開層次
    draw.rounded_rectangle([4, 4, width - 4, height - 4], radius=RADIUS + 4, fill=CARD_COLOR)

    # 標題橫幅（薄荷藍為主色，兩側各點綴一個音符，呼應「音樂系 bot」的品牌識別）
    title_font = _font(18)
    draw.rounded_rectangle([MARGIN, MARGIN, width - MARGIN, MARGIN + HEADER_H - 8],
                            radius=RADIUS, fill=HEADER_BAND)
    title = f"{year}.{month:02d} Check-in Calendar"
    title_cy = MARGIN + (HEADER_H - 8) / 2
    draw.text((width / 2, title_cy), title, fill=MIKU_TEAL_DEEP, font=title_font, anchor="mm", stroke_width=1, stroke_fill=MIKU_TEAL_DEEP)
    _draw_note(draw, MARGIN + 22, title_cy + 3, 7, MIKU_TEAL_DEEP)
    _draw_note(draw, width - MARGIN - 22, title_cy + 3, 7, MIKU_TEAL_DEEP)

    # 星期標題（週末跟平日用不同的膠囊底色區分）
    weekday_font = _font(13)
    grid_top = MARGIN + HEADER_H
    for i, label in enumerate(WEEKDAY_LABELS):
        x0 = MARGIN + i * CELL_W + 4
        x1 = MARGIN + (i + 1) * CELL_W - 4
        pill_color = WEEKEND_PILL if i in (0, 6) else WEEKDAY_PILL
        draw.rounded_rectangle([x0, grid_top + 2, x1, grid_top + WEEKDAY_H - 2], radius=9, fill=pill_color)
        cx = MARGIN + i * CELL_W + CELL_W / 2
        draw.text((cx, grid_top + WEEKDAY_H / 2), label, fill=MIKU_TEAL_DEEP, font=weekday_font, anchor="mm")

    grid_top += WEEKDAY_H
    day_font = _font(13)
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
            cell_fill = CELL_CHECKED_COLOR if checked else CELL_COLOR
            draw.rounded_rectangle([x0, y0, x1, y1], radius=RADIUS, fill=cell_fill, outline=GRID_COLOR, width=1)

            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

            if checked:
                stamp_r = min(CELL_W, CELL_H) / 2 - 8
                _stamp_checkin_cell(img, draw, cx, cy + 2, stamp_r)
                draw.text((x1 - 6, y0 + 5), str(day), fill=MUTED_TEXT, font=day_font, anchor="ra")
            else:
                draw.text((x0 + 8, y0 + 6), str(day), fill=TEXT_COLOR, font=day_font, anchor="la")

            if date_str == today_str:
                draw.rounded_rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], radius=RADIUS - 1,
                                        outline=TODAY_BORDER, width=3)
                _draw_star(draw, x1 - 9, y0 + 10, r_outer=7, r_inner=3, fill=STAR_COLOR)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
