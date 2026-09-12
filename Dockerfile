FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt requirements-cloud.txt ./
RUN python -m pip install -r requirements-cloud.txt

COPY . .

RUN adduser --disabled-password --gecos "" --uid 10001 taggy
USER taggy

CMD ["sh", "-c", "exec uvicorn cloudrun_main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
