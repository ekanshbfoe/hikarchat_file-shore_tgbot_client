"""Reads the text in a screenshot, quickly. Tuned for speed over perfect accuracy:
small greyscale image, Tesseract's fast mode, one thread, and a hard time limit."""

import asyncio
import io
import logging
import os

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)
TARGET_WIDTH = 1000
MAX_PIXELS = 40_000_000
ENGLISH = "eng"
HINDI = "hin"

# One at a time, so a burst of screenshots can't exhaust a small server's memory.
_limit = asyncio.Semaphore(1)


class NotAnImageError(Exception):
    pass


def prepare_image(data: bytes) -> bytes:
    """Shrink, greyscale, and make the text dark on light, which Tesseract reads best."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as image:
            grey = ImageOps.exif_transpose(image).convert("L")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise NotAnImageError from error
    if grey.width > TARGET_WIDTH:
        height = round(grey.height * TARGET_WIDTH / grey.width)
        grey = grey.resize((TARGET_WIDTH, height), Image.Resampling.BILINEAR)
    # Dark mode screenshots: flip them.
    histogram = grey.histogram()
    mean = sum(value * count for value, count in enumerate(histogram)) / max(sum(histogram), 1)
    if mean < 110:
        grey = ImageOps.invert(grey)
    output = io.BytesIO()
    grey.save(output, format="PNG", compress_level=1)
    return output.getvalue()


async def _run_tesseract(image: bytes, language: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "tesseract",
        "stdin",
        "stdout",
        "-l",
        language,
        "--oem",
        "1",  # The neural engine only; the legacy data isn't installed.
        "--psm",
        "11",  # Sparse text: app screens are scattered labels, not paragraphs.
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    try:
        output, _ = await process.communicate(image)
    except asyncio.CancelledError:
        # The time limit fired. Don't leave the program running.
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()
        raise
    if process.returncode != 0:
        raise RuntimeError(f"tesseract exited with {process.returncode}")
    return output.decode("utf-8", "ignore")


async def read_text(image: bytes, language: str) -> str:
    async with _limit:
        return await _run_tesseract(image, language)
