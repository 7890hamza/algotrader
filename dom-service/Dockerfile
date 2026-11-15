# Memory DOM: takes NinjaTrader's DOM feed (TCP 8060) and serves the ladder (HTTP 8030).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=America/Los_Angeles
WORKDIR /app
COPY dom-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY dom-service/ /app/
EXPOSE 8030 8060
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8030"]
