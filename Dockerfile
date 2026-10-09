FROM python:3.11-slim

WORKDIR /srv
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY eval ./eval

ENV KALDERA_SCENARIOS=/srv/eval/scenarios.jsonl \
    PARTENAIRE_URL=http://partenaire:8100

# Port d'écoute : $PORT s'il est fourni (Cloud Run l'impose), 8000 sinon (docker compose).
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/api/bornes')"
CMD ["sh", "-c", "exec uvicorn kaldera.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
