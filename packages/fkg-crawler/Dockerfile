FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/fkg-common packages/fkg-common
COPY packages/fkg-normalizer packages/fkg-normalizer
COPY packages/fkg-rules packages/fkg-rules
COPY packages/fkg-dedup packages/fkg-dedup
COPY packages/fkg-agents packages/fkg-agents
COPY packages/fkg-crawler packages/fkg-crawler

RUN pip install --no-cache-dir \
    -e packages/fkg-common \
    -e packages/fkg-normalizer \
    -e packages/fkg-rules \
    -e packages/fkg-dedup \
    -e packages/fkg-agents \
    -e packages/fkg-crawler

CMD ["python", "-m", "fkg_crawler.worker"]
