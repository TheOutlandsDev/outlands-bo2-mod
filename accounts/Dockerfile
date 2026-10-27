FROM python:3.12-slim-bookworm
WORKDIR /app
COPY accounts/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY accounts/ /app/accounts/
COPY portal/portal.py /app/portal/portal.py
RUN mkdir -m 700 /accounts /run/outlands /agent-secrets && chown 10001:10001 /accounts /run/outlands /agent-secrets
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENTRYPOINT ["python3","-B","/app/accounts/service.py"]
