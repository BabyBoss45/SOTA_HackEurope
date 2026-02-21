FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./agents/
RUN pip install --no-cache-dir -r agents/requirements.txt

COPY . ./agents/
RUN pip install -e ./agents/

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
RUN playwright install chromium --with-deps

RUN useradd -m -u 1000 appuser
USER appuser

CMD ["python", "agents/butler_api.py"]
