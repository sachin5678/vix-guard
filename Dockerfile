FROM python:3.12-slim

WORKDIR /app
COPY vixguard ./vixguard

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "vixguard", "run"]
