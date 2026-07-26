FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY packages/fkg-common packages/fkg-common
COPY packages/fkg-api packages/fkg-api

RUN pip install --no-cache-dir -e packages/fkg-common -e packages/fkg-api

EXPOSE 8000

CMD ["uvicorn", "fkg_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
