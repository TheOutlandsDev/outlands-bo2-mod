FROM python:3.12-slim-bookworm
WORKDIR /app
COPY portal/portal.py /app/portal.py
COPY portal/web /app/web
COPY ai/personalities.json /app/personalities.json
COPY storage/t6/outlands_rotation.json /app/maps.json
RUN mkdir /public && chown 10001:10001 /public
USER 10001:10001
ENTRYPOINT ["python3", "-B", "/app/portal.py"]
CMD ["serve"]
