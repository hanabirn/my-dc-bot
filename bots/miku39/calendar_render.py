# calendar_render.py
# 把 /簽到 的紀錄畫成一張真的月曆圖：已簽到的日期會蓋上一個 Miku 印章（圓圈+音符），
# 今天的格子會有粉色外框。星期標題故意用英文縮寫（Sun/Mon/...），不用「日一二三」，
# 是因為 PIL 內建字型（load_default）不支援中文字，會直接顯示空白方塊；要顯示中文
# 得額外打包一個 TTF 字型檔進 repo，這裡先用英文縮寫避免那個風險。
import calendar as cal_module
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

MIKU_TEAL = (57, 197, 187)
BG_COLOR = (250, 248, 252)
GRID_COLOR = (222, 212, 236)
TEXT_COLOR = (70, 60, 90)
MUTED_TEXT = (170, 160, 190)
TODAY_BORDER = (244, 114, 182)

WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

CELL_W = 60
CELL_H = 54
HEADER_H = 44
WEEKDAY_H = 26
MARGIN = 12


def render_checkin_calendar(year: int, month: int, checked_dates: set, today_str: str) -> BytesIO:
    """畫出 year/month 那個月的簽到行事曆。checked_dates 是 'YYYY-MM-DD' 字串
    的集合，today_str 是今天的日期字串。回傳可直接當 discord.File 附件送出的
    PNG bytes（呼叫端記得 seek(0) 已經處理好，直接用就好）。"""
    cal_module.setfirstweekday(cal_module.SUNDAY)
    weeks = cal_module.monthcalendar(year, month)

    width = MARGIN * 2 + CELL_W * 7
    height = MARGIN * 2 + HEADER_H + WEEKDAY_H + CELL_H * len(weeks)

    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    title = f"{year}-{month:02d} Check-in Calendar"
    draw.text((width / 2, MARGIN + HEADER_H / 2), title, fill=TEXT_COLOR, font=font, anchor="mm")

    grid_top = MARGIN + HEADER_H
    for i, label in enumerate(WEEKDAY_LABELS):
        x = MARGIN + i * CELL_W + CELL_W / 2
        draw.text((x, grid_top + WEEKDAY_H / 2), label, fill=MUTED_TEXT, font=font, anchor="mm")

    grid_top += WEEKDAY_H
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x0 = MARGIN + c * CELL_W
            y0 = grid_top + r * CELL_H
            x1 = x0 + CELL_W
            y1 = y0 + CELL_H
            draw.rectangle([x0, y0, x1, y1], outline=GRID_COLOR, width=1)
            if day == 0:
                continue

            date_str = f"{year:04d}-{month:02d}-{day:02d}"
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            checked = date_str in checked_dates

            if checked:
                # 印章樣式：實心圓+白色日期數字，PIL 內建字型不支援 ♪ 這種符號
                # （會印出空白方塊），乾脆改成真的「蓋章」感覺，日期還是看得到
                stamp_r = min(CELL_W, CELL_H) / 2 - 6
                draw.ellipse(
                    [cx - stamp_r, cy - stamp_r, cx + stamp_r, cy + stamp_r],
                    fill=MIKU_TEAL
                )
                draw.text((cx, cy), str(day), fill=(255, 255, 255), font=font, anchor="mm")
            else:
                draw.text((cx, y0 + 12), str(day), fill=TEXT_COLOR, font=font, anchor="mm")

            if date_str == today_str:
                draw.rectangle([x0 + 2, y0 + 2, x1 - 2, y1 - 2], outline=TODAY_BORDER, width=2)

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
