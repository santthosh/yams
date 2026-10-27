FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY infra/docker/backend-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
COPY pyproject.toml ./
COPY backend ./backend
COPY data/fixtures ./data/fixtures
COPY infra/docker/entrypoint.sh /usr/local/bin/yams-entrypoint
COPY scripts/container_bootstrap.py /app/container_bootstrap.py
RUN chmod 755 /usr/local/bin/yams-entrypoint && mkdir /artifacts && chown 65534:65534 /artifacts
USER 65534:65534
ENTRYPOINT ["yams-entrypoint"]
CMD ["api"]
