# calendar_render.py
# 把 /簽到 的紀錄畫成一張卡通風格的月曆圖：圓角卡片、粉嫩色系，已簽到的日期會蓋上
# 一個Q版初音未來小貼圖印章，今天的格子會有粉色外框+一顆小星星。星期標題故意用
# 英文縮寫（Sun/Mon/...），Miku 的臉部五官（眼睛/嘴巴/腮紅）也全部用 PIL 圖形基本
# 元素（橢圓/線段/多邊形）畫出來，不用文字符號——是因為 PIL 內建字型（load_default）
# 不支援中文字或 ☆♪ 這類符號，會直接顯示空白方塊；要顯示這些得額外打包一個 TTF
# 字型檔或圖片素材進 repo，這裡全部用向量圖形畫，同時避免了外部圖片素材連結可能
# 失效的風險。Pillow 10.1+ 的 load_default(size=...) 可以縮放內建字型且維持清晰
# （不是像素化放大），所以標題/日期數字可以做得比舊版大一些、更像卡通風格。
import calendar as cal_module
import math
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

MIKU_TEAL = (57, 197, 187)
MIKU_TEAL_SOFT = (163, 230, 222)
BG_COLOR = (255, 250, 252)
CARD_COLOR = (255, 255, 255)
CELL_COLOR = (250, 247, 252)
CELL_CHECKED_COLOR = (232, 250, 247)
GRID_COLOR = (230, 221, 240)
TEXT_COLOR = (86, 74, 104)
MUTED_TEXT = (176, 166, 196)
TODAY_BORDER = (244, 114, 182)
STAR_COLOR = (255, 200, 87)
HEADER_BAND = (255, 224, 235)
WEEKEND_PILL = (255, 214, 231)
WEEKDAY_PILL = (222, 240, 238)
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


def _font(size):
    return ImageFont.load_default(size=size)


def _draw_star(draw, cx, cy, r_outer, r_inner, fill, points=5):
    verts = []
    for i in range(points * 2):
        r = r_outer if i % 2 == 0 else r_inner
        angle = math.pi / points * i - math.pi / 2
        verts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(verts, fill=fill)


def _draw_miku_stamp(draw, cx, cy, r):
    """畫一個Q版初音未來小貼圖：雙馬尾+圓臉+瞇瞇笑眼+腮紅，全部用基本圖形拼出來，
    尺寸抓 stamp 半徑 r 的比例去算，改 r 不用重新調整每個部件的位置。"""
    # 雙馬尾（畫在最底層，露出臉的兩側跟下面一截）
    tail_w = r * 0.42
    draw.ellipse([cx - r * 1.15 - tail_w / 2, cy - r * 0.55, cx - r * 1.15 + tail_w / 2, cy + r * 0.95],
                 fill=MIKU_TEAL)
    draw.ellipse([cx + r * 1.15 - tail_w / 2, cy - r * 0.55, cx + r * 1.15 + tail_w / 2, cy + r * 0.95],
                 fill=MIKU_TEAL)

    # 後髮（比臉大一圈的瀏海輪廓，臉畫上去之後只會露出上緣一圈當髮際線）
    draw.ellipse([cx - r * 0.92, cy - r * 0.95, cx + r * 0.92, cy + r * 0.5], fill=MIKU_TEAL)

    # 臉（膚色，蓋在後髮上面，只留髮際線一圈跟兩側馬尾露出來）
    face_r = r * 0.72
    draw.ellipse([cx - face_r, cy - face_r * 0.78, cx + face_r, cy + face_r * 1.05], fill=SKIN_COLOR)

    # 瀏海尖角（幾個小三角形貼在髮際線上，增加一點髮絲感）
    for dx in (-0.42, -0.1, 0.22, 0.5):
        bx = cx + r * dx
        by = cy - face_r * 0.78 + r * 0.06
        draw.polygon([(bx - r * 0.14, by), (bx + r * 0.14, by), (bx, by + r * 0.32)], fill=MIKU_TEAL)

    # 腮紅
    blush_r = r * 0.13
    draw.ellipse([cx - face_r * 0.72 - blush_r, cy + r * 0.12 - blush_r,
                  cx - face_r * 0.72 + blush_r, cy + r * 0.12 + blush_r], fill=BLUSH_COLOR)
    draw.ellipse([cx + face_r * 0.72 - blush_r, cy + r * 0.12 - blush_r,
                  cx + face_r * 0.72 + blush_r, cy + r * 0.12 + blush_r], fill=BLUSH_COLOR)

    # 瞇瞇笑眼（^ ^，兩段短線拼成一個尖角）
    eye_w = r * 0.22
    eye_y = cy - r * 0.02
    lw = max(1, round(r * 0.09))
    for ex in (cx - face_r * 0.4, cx + face_r * 0.4):
        draw.line([(ex - eye_w / 2, eye_y + r * 0.1), (ex, eye_y - r * 0.08)], fill=FACE_LINE, width=lw)
        draw.line([(ex, eye_y - r * 0.08), (ex + eye_w / 2, eye_y + r * 0.1)], fill=FACE_LINE, width=lw)

    # 微笑嘴（小小一段往下彎的弧線）
    mouth_w = r * 0.34
    mouth_y = cy + r * 0.32
    draw.arc([cx - mouth_w / 2, mouth_y - r * 0.16, cx + mouth_w / 2, mouth_y + r * 0.22],
              start=20, end=160, fill=FACE_LINE, width=max(1, round(r * 0.08)))


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

    # 標題橫幅
    title_font = _font(18)
    draw.rounded_rectangle([MARGIN, MARGIN, width - MARGIN, MARGIN + HEADER_H - 8],
                            radius=RADIUS, fill=HEADER_BAND)
    title = f"{year}.{month:02d} Check-in Calendar"
    draw.text((width / 2, MARGIN + (HEADER_H - 8) / 2), title, fill=TEXT_COLOR, font=title_font, anchor="mm")

    # 星期標題（週末跟平日用不同的膠囊底色區分）
    weekday_font = _font(13)
    grid_top = MARGIN + HEADER_H
    for i, label in enumerate(WEEKDAY_LABELS):
        x0 = MARGIN + i * CELL_W + 4
        x1 = MARGIN + (i + 1) * CELL_W - 4
        pill_color = WEEKEND_PILL if i in (0, 6) else WEEKDAY_PILL
        draw.rounded_rectangle([x0, grid_top + 2, x1, grid_top + WEEKDAY_H - 2], radius=9, fill=pill_color)
        cx = MARGIN + i * CELL_W + CELL_W / 2
        draw.text((cx, grid_top + WEEKDAY_H / 2), label, fill=TEXT_COLOR, font=weekday_font, anchor="mm")

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
                _draw_miku_stamp(draw, cx, cy + 2, stamp_r)
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
