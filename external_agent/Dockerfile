FROM python:3.11-slim

WORKDIR /srv
RUN pip install --no-cache-dir "fastapi>=0.115,<0.120" "uvicorn[standard]>=0.30,<0.40"
COPY . /srv/external_agent

EXPOSE 8100
CMD ["uvicorn", "external_agent.app:app", "--host", "0.0.0.0", "--port", "8100"]
