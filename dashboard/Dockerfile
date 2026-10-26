ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/gateway/src:/app/sandbox_tools/src
WORKDIR /app
COPY wheelhouse/ /wheelhouse/
COPY gateway/central-test.lock /app/gateway/central-test.lock
RUN python -m pip install --no-index --find-links=/wheelhouse -r gateway/central-test.lock
COPY . /app/
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "chainguard_gateway.audit_console", "--host", "0.0.0.0"]
