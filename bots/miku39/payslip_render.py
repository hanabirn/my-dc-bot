# payslip_render.py
# /打工 的薪資單視覺化：畫一張收據樣式的圖，顯示今天做的工作、底薪、有沒有觸發
# 特殊事件（加班費/驚喜禮物/扣薪），跟 calendar_render.py 一樣全部用英文字，
# 原因相同：PIL 內建字型不支援中文字，會印出空白方塊。
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

MIKU_TEAL = (57, 197, 187)
BG_COLOR = (250, 248, 252)
TEXT_COLOR = (70, 60, 90)
MUTED_TEXT = (170, 160, 190)
LINE_COLOR = (222, 212, 236)
POSITIVE_COLOR = (57, 197, 187)
NEGATIVE_COLOR = (244, 114, 182)

WIDTH = 300
PADDING = 20


def render_payslip(job_label: str, date_str: str, base_exp: int, bonus_label: str, bonus_delta: int, total_exp: int) -> BytesIO:
    """畫一張打工薪資單。bonus_label 是特殊事件的英文說明（沒觸發就傳 None），
    bonus_delta 是事件造成的經驗值增減（可以是負的）。回傳可直接當
    discord.File 附件送出的 PNG bytes。"""
    font = ImageFont.load_default()
    stamp_r = 26
    # 逐行往下疊加算出實際需要的高度，最後再加印章的半徑+留白，
    # 之前用猜的固定高度把印章的下半部切掉了。
    content_bottom = PADDING + 20 + 16 + 18 + 22 + 16 + 18 + (22 if bonus_label else 0) + 18 + 30
    height = content_bottom + stamp_r + PADDING

    img = Image.new("RGB", (WIDTH, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PADDING
    draw.text((WIDTH / 2, y), "MIKU39 PAYSLIP", fill=TEXT_COLOR, font=font, anchor="mm")
    y += 20
    draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=LINE_COLOR, width=1)
    y += 16

    draw.text((PADDING, y), "Job:", fill=MUTED_TEXT, font=font, anchor="lm")
    draw.text((WIDTH - PADDING, y), job_label, fill=TEXT_COLOR, font=font, anchor="rm")
    y += 18
    draw.text((PADDING, y), "Date:", fill=MUTED_TEXT, font=font, anchor="lm")
    draw.text((WIDTH - PADDING, y), date_str, fill=TEXT_COLOR, font=font, anchor="rm")
    y += 22

    draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=LINE_COLOR, width=1)
    y += 16

    draw.text((PADDING, y), "Base Pay", fill=MUTED_TEXT, font=font, anchor="lm")
    draw.text((WIDTH - PADDING, y), f"+{base_exp} EXP", fill=TEXT_COLOR, font=font, anchor="rm")
    y += 18

    if bonus_label:
        color = POSITIVE_COLOR if bonus_delta >= 0 else NEGATIVE_COLOR
        sign = "+" if bonus_delta >= 0 else ""
        draw.text((PADDING, y), bonus_label, fill=color, font=font, anchor="lm")
        draw.text((WIDTH - PADDING, y), f"{sign}{bonus_delta} EXP", fill=color, font=font, anchor="rm")
        y += 22

    draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=LINE_COLOR, width=1)
    y += 18

    draw.text((PADDING, y), "TOTAL", fill=TEXT_COLOR, font=font, anchor="lm")
    draw.text((WIDTH - PADDING, y), f"+{total_exp} EXP", fill=MIKU_TEAL, font=font, anchor="rm")
    y += 30

    # 印章：核可章，蓋在右下角
    stamp_cx, stamp_cy = WIDTH - PADDING - stamp_r, y
    draw.ellipse(
        [stamp_cx - stamp_r, stamp_cy - stamp_r, stamp_cx + stamp_r, stamp_cy + stamp_r],
        outline=MIKU_TEAL, width=3
    )
    draw.text((stamp_cx, stamp_cy), "OK", fill=MIKU_TEAL, font=font, anchor="mm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
