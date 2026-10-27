FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/outlands-chat
COPY bridge.py careers.py operations.py armory.py tactics.py benchmark.py conversation_benchmark.py config.example.json personalities.json ./
RUN mkdir -m 700 /rivals && chown 10001:10001 /rivals
USER 10001:10001
ENTRYPOINT ["python3", "/opt/outlands-chat/bridge.py"]
