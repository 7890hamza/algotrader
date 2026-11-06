# The Lab: two agents run by a small harness. Light on purpose: numpy only for now.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=America/Los_Angeles
WORKDIR /lab
COPY lab/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
CMD ["python", "harness.py"]
