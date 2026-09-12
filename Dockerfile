FROM python:3.13-slim

# Keep native numerical/video libraries from creating a large CPU thread pool
# inside every Streamlit session. Cloud Run scales sessions across instances.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY . .

RUN adduser --disabled-password --gecos "" --uid 10001 taggy \
    && mkdir -p /app/.tmp \
    && chown -R taggy:taggy /app
USER taggy

CMD ["sh", "-c", "exec python -m streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8080} --server.headless=true --browser.gatherUsageStats=false"]
