ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/gateway/src:/app/sandbox_tools/src
WORKDIR /app
COPY wheelhouse/ /wheelhouse/
COPY gateway/central-test.lock /app/gateway/central-test.lock
RUN python -m pip install --no-index --find-links=/wheelhouse -r gateway/central-test.lock
COPY gateway/src/ /app/gateway/src/
COPY gateway/integration/ /app/gateway/integration/
COPY sandbox_tools/src/ /app/sandbox_tools/src/
COPY sandbox_tools/tests/ /app/sandbox_tools/tests/
COPY spec/ /app/spec/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY contracts/interfaces/ /app/contracts/interfaces/
COPY scripts/build_specs.py /app/scripts/build_specs.py
RUN mkdir /sandbox && chown 10001:10001 /sandbox && chmod 700 /sandbox
USER 10001:10001
CMD ["python", "-m", "pytest", "gateway/integration/test_central.py", "-q", "-p", "no:cacheprovider"]
