FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

EXPOSE 19999 20000-21000

CMD ["python", "-m", "silc", "daemon"]
