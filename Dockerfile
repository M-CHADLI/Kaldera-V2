FROM python:3.11-slim

WORKDIR /srv
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY eval ./eval

ENV KALDERA_SCENARIOS=/srv/eval/scenarios.jsonl \
    PARTENAIRE_URL=http://partenaire:8100

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=5s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/bornes')"
CMD ["uvicorn", "kaldera.web:app", "--host", "0.0.0.0", "--port", "8000"]
