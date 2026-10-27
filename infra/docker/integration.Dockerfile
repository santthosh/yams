FROM python:3.13.12-slim@sha256:f1927c75e81efd1e091dbd64b6c0ecaa5630b38635a3d1c04034ac636e1f94c8
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY infra/docker/integration-requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
COPY pyproject.toml ./
COPY backend ./backend
COPY data/fixtures ./data/fixtures
RUN mkdir /evidence && chmod 1777 /evidence
USER 65534:65534
CMD ["python", "-m", "pytest", "backend/tests/integration", "-m", "integration and not restart_verify", "-p", "no:cacheprovider"]
