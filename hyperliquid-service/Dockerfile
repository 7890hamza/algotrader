# Hyperliquid (read-only): copies trade.xyz XYZ100 / SP500 1-minute candles into the database.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY hyperliquid-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY hyperliquid-service/ /app/
EXPOSE 8040
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8040"]
