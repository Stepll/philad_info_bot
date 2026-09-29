"""Генерація картинки розкладу на тиждень."""

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.schedule import COLORS, DAYS_SHORT, DEFAULT_COLOR, ScheduleItem

FONTS = Path(__file__).parent / "assets" / "fonts"

# Розміри задані для 1280x720 і множаться на SCALE
SCALE = 1.5
WIDTH, MIN_HEIGHT = 1280, 720
HEADER_Y = 72
AREA_TOP = 128
AREA_BOTTOM = 690
CARD_GAP = 2
CARD_RADIUS = 16
PAD_X, PAD_TOP, PAD_BOTTOM = 20, 18, 20
TITLE_SIZE, TIME_SIZE, HEADER_SIZE = 19, 19, 30
TITLE_LINE_H = 21
TITLE_TIME_GAP = 12

BG = (17, 25, 30)
STRIPE = (255, 255, 255, 5)  # легке підсвічування парних колонок


def _s(v: float) -> int:
    return round(v * SCALE)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Inter-{name}.ttf"), _s(size))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=font) <= max_w or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _background(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), BG)
    # Зернистість як у референсі
    noise = Image.effect_noise((w, h), 18).point(lambda v: max(0, v - 128) // 2)
    img = Image.composite(Image.new("RGB", (w, h), (70, 90, 95)), img, noise)
    return img


def render_schedule(items: list[ScheduleItem]) -> bytes:
    title_font = _font("SemiBold", TITLE_SIZE)
    time_font = _font("Regular", TIME_SIZE)
    header_font = _font("Regular", HEADER_SIZE)

    col_w = WIDTH / 7
    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # Розмітка карток: висота залежить від кількості рядків назви
    cards = []
    for item in items:
        lines = _wrap(scratch, item.title, title_font, _s(col_w - 2 * PAD_X))
        height = PAD_TOP + len(lines) * TITLE_LINE_H + TITLE_TIME_GAP + TIME_SIZE + PAD_BOTTOM
        cards.append((item, lines, height))

    # Вертикальна позиція — за часом початку (лінійно між найранішим і найпізнішим)
    if items:
        t_min = min(i.minutes for i in items)
        t_max = max(i.minutes for i in items)
    else:
        t_min = t_max = 0
    max_card_h = max((h for _, _, h in cards), default=0)
    span = AREA_BOTTOM - AREA_TOP - max_card_h

    placed = []
    bottom_edge = MIN_HEIGHT
    for day in range(7):
        prev_bottom = AREA_TOP - CARD_GAP
        day_cards = sorted((c for c in cards if c[0].day == day), key=lambda c: (c[0].minutes, c[0].id))
        for item, lines, h in day_cards:
            ratio = (item.minutes - t_min) / (t_max - t_min) if t_max > t_min else 0
            y = max(AREA_TOP + ratio * span, prev_bottom + CARD_GAP)  # не накладаємо картки
            placed.append((item, lines, day, y, h))
            prev_bottom = y + h
            bottom_edge = max(bottom_edge, prev_bottom + 30)

    w, h = _s(WIDTH), _s(bottom_edge)
    img = _background(w, h).convert("RGBA")

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for day in range(1, 7, 2):
        od.rectangle([_s(day * col_w), 0, _s((day + 1) * col_w), h], fill=STRIPE)
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)
    for day, label in enumerate(DAYS_SHORT):
        draw.text((_s((day + 0.5) * col_w), _s(HEADER_Y)), label, font=header_font, fill="white", anchor="mm")

    for item, lines, day, y, card_h in placed:
        color = COLORS.get(item.color) or COLORS[DEFAULT_COLOR]
        x0 = day * col_w
        draw.rounded_rectangle(
            [_s(x0), _s(y), _s(x0 + col_w), _s(y + card_h)], radius=_s(CARD_RADIUS), fill=color.bg
        )
        ty = y + PAD_TOP
        for line in lines:
            draw.text((_s(x0 + PAD_X), _s(ty)), line, font=title_font, fill=color.fg)
            ty += TITLE_LINE_H
        draw.text((_s(x0 + PAD_X), _s(ty + TITLE_TIME_GAP)), item.time, font=time_font, fill=color.fg)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


if __name__ == "__main__":
    # Швидкий перегляд: python -m bot.schedule_image out.jpg
    import sys

    from bot.schedule import SEED

    demo = [ScheduleItem(i, d, t, title, c) for i, (d, t, title, c) in enumerate(SEED)]
    Path(sys.argv[1] if len(sys.argv) > 1 else "schedule.jpg").write_bytes(render_schedule(demo))
