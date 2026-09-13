FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY resources ./resources
RUN pip install --no-cache-dir .
COPY .env.example ./.env.example
CMD ["python", "-m", "pixelpilot.main"]
