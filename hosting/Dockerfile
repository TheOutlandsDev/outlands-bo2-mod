# syntax=docker/dockerfile:1
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates fonts-liberation libgl1-mesa-dri \
       python3 tini wine wine32:i386 wine64 winbind xauth xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --home-dir /home/t6 --shell /usr/sbin/nologin t6 \
    && mkdir -p /data /opt/t6 \
    && chown t6:t6 /data

# Only vendor-manifest files enter this additional build context.
# Client login/configuration, private server keys and player saves are excluded.
COPY --from=plutonium --chown=10001:10001 / /opt/t6/plutonium/

# This private image intentionally includes the full, locally owned game.
COPY --from=game /zone/ /opt/t6/game/zone/
COPY --from=game /sound/ /opt/t6/game/sound/
COPY --from=game /video/ /opt/t6/game/video/
COPY --from=game /redist/ /opt/t6/game/redist/
COPY --from=game /Soundtrack/ /opt/t6/game/Soundtrack/
COPY --from=game ["/t6mp.exe", "/t6sp.exe", "/binkw32.dll", "/steam_api.dll", "/localization.txt", "/localization_mp.txt", "/codlogo.bmp", "/installscript.vdf", "/opt/t6/game/"]

COPY --chown=10001:10001 storage/ /opt/t6/mod/storage/
COPY --chmod=755 hosting/entrypoint.py /opt/t6/entrypoint.py
COPY hosting/rotation.py /opt/t6/rotation.py
COPY --chmod=755 hosting/healthcheck.py /opt/t6/healthcheck.py
COPY --chmod=755 hosting/store_key.py /opt/t6/store_key.py

ENV HOME=/home/t6 USER=t6 WINEPREFIX=/data/prefix WINEARCH=win64 \
    WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=" \
    XDG_CACHE_HOME=/data/cache PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
WORKDIR /data
STOPSIGNAL SIGTERM
HEALTHCHECK --start-period=180s --interval=30s --timeout=5s --retries=3 \
    CMD ["python3", "/opt/t6/healthcheck.py"]
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/bin/xvfb-run", "-a", "-s", "-screen 0 800x600x24 -nolisten tcp", "python3", "-u", "/opt/t6/entrypoint.py"]
