FROM python:3.13-slim

# tesseract-ocr-eng ships the fast models, which is what the screenshot check wants.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY bot ./bot
COPY migrations ./migrations
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
# The disk is wiped on every restart; this file is only ever a cache.
ENV LOCAL_CACHE_PATH=/tmp/local_cache.sqlite3

RUN useradd --create-home bot
USER bot

CMD ["python", "-m", "bot.main"]
