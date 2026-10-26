ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/gateway/src CHG_HOST=0.0.0.0 CHG_APP_ENV=container
WORKDIR /app
COPY gateway/requirements.lock /app/gateway/requirements.lock
RUN python -m pip install --no-cache-dir -r gateway/requirements.lock
COPY gateway/src /app/gateway/src
COPY spec /app/spec
COPY config /app/config
COPY docs /app/docs
COPY contracts/interfaces /app/contracts/interfaces
COPY scripts/build_specs.py /app/scripts/build_specs.py
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin chainguard
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=6 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2).read()"]
CMD ["python", "-m", "chainguard_gateway"]
