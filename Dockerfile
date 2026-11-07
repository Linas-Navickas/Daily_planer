FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN useradd --system --uid 10001 --create-home appuser

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser main.py mcp_server.py database.py schemas.py index.html app.js alembic.ini ./
COPY --chown=appuser:appuser migrations ./migrations

USER appuser

EXPOSE 8000 8001

CMD ["python", "main.py"]
