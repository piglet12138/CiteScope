FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir tldextract>=5.1.0

# Copy app
COPY app/ ./app/
COPY scripts/ ./scripts/

RUN mkdir -p /app/data /app/data/screenshots

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
