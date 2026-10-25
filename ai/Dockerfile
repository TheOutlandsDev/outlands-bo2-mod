FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/outlands-chat
COPY bridge.py config.example.json personalities.json ./
USER 10001:10001
ENTRYPOINT ["python3", "/opt/outlands-chat/bridge.py"]
