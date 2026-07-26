FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages packages
COPY tests tests

RUN pip install --no-cache-dir \
    -e packages/fkg-common \
    -e packages/fkg-normalizer \
    -e packages/fkg-rules \
    -e packages/fkg-dedup \
    -e packages/fkg-agents \
    pytest \
    jinja2 \
    httpx

CMD ["python", "-m", "pytest", "tests/unit", "-v"]
