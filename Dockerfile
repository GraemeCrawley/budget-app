FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# Build context is the repo ROOT (deploy/compose.yml uses `build: ..`).
# .dockerignore MUST exclude private/ and .git so real financial data and
# history never enter the image. requirements first for layer caching.
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Connectors (statement parsers), the server and its schema, and the client built above.
COPY connectors/ ./connectors/
COPY tracker/ ./tracker/
COPY --from=web /web/dist ./web_dist

EXPOSE 8000

# No access log: it would record query strings (a category, a month).
CMD ["uvicorn", "tracker.server:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
