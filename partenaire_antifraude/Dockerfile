FROM python:3.11-slim

WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115,<0.120" "uvicorn[standard]>=0.30,<0.40"
COPY app.py /srv/partenaire_antifraude/app.py
COPY __init__.py /srv/partenaire_antifraude/__init__.py

# Cloud Run fournit le port dans $PORT (8080 par défaut).
ENV PORT=8080
CMD exec uvicorn partenaire_antifraude.app:app --host 0.0.0.0 --port ${PORT}
