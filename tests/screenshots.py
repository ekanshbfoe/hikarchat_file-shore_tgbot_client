"""Draws phone-style screenshots so the real OCR engine can be exercised without real
samples. They're approximations of the apps' layouts, not the real thing."""

import io

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _font(size, bold=False):
    return ImageFont.truetype(BOLD_PATH if bold else FONT_PATH, size)


def _screen(lines, dark=False, size=(1080, 2200), clock=True) -> bytes:
    background, ink, button = (
        ((15, 15, 15), (240, 240, 240), (60, 60, 60))
        if dark
        else ((255, 255, 255), (20, 20, 20), (235, 235, 235))
    )
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    if clock:
        draw.text((40, 20), "10:47 AM", fill=ink, font=_font(34))
    for y, text, font_size, is_button in lines:
        if is_button:
            width = draw.textlength(text, font=_font(font_size, True))
            draw.rounded_rectangle(
                (60, y - 15, 60 + width + 80, y + font_size + 20), radius=30, fill=button
            )
            draw.text((100, y), text, fill=ink, font=_font(font_size, True))
        else:
            draw.text((60, y), text, fill=ink, font=_font(font_size))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=85)
    return output.getvalue()


def youtube(name="Cool Edits", handle="@cooledits", subscribed=True, dark=False, clock=True):
    return _screen(
        [
            (500, name, 56, False),
            (580, f"{handle}  1.2M subscribers  340 videos", 34, False),
            (650, "Editing tutorials and project files", 34, False),
            (760, "Subscribed" if subscribed else "Subscribe", 42, True),
            (900, "Home   Videos   Shorts   Playlists", 38, False),
            (1100, "How to make smooth transitions", 40, False),
        ],
        dark=dark,
        clock=clock,
    )


def tiktok(name="Cool Edits", handle="@cooledits", state="following", dark=False):
    button = {"following": "Message", "friends": "Friends", "not": "Follow"}[state]
    return _screen(
        [
            (420, handle, 44, False),
            (520, f"{name}", 40, False),
            (620, "123 Following    45K Followers    1M Likes", 34, False),
            (740, button, 42, True),
            (900, "Project files in bio", 34, False),
        ],
        dark=dark,
    )


def unrelated():
    return _screen(
        [(600, "Weather today", 60, False), (720, "Sunny and warm", 40, False)], clock=False
    )


def blank():
    return _screen([], clock=False)
