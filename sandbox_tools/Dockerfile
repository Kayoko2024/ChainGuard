ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/sandbox_tools/src
WORKDIR /app
COPY sandbox_tools/src/ sandbox_tools/src/
COPY sandbox_tools/tests/ sandbox_tools/tests/
COPY spec/schemas/protocol.schema.json spec/schemas/protocol.schema.json
COPY scripts/phase2_evidence.py scripts/phase2_evidence.py
RUN mkdir /sandbox && chown 10001:10001 /sandbox && chmod 700 /sandbox
USER 10001:10001
CMD ["python", "-m", "unittest", "discover", "-s", "sandbox_tools/tests", "-p", "test_resources.py", "-v"]
