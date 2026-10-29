FROM public.ecr.aws/docker/library/python:3.14.4-slim-bookworm@sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
ARG DEBIAN_HOST=deb.debian.org
RUN sed -i "s|http://deb.debian.org|https://${DEBIAN_HOST}|g" /etc/apt/sources.list.d/debian.sources && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 update && apt-get -o Acquire::Retries=2 -o Acquire::https::Timeout=30 install -y --no-install-recommends libreoffice-writer poppler-utils fonts-wqy-zenhei && rm -rf /var/lib/apt/lists/*
COPY document_tools/requirements.txt /app/requirements.txt
ARG PYPI_INDEX=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url ${PYPI_INDEX} -r /app/requirements.txt
COPY document_tools/worker.py /app/worker.py
WORKDIR /tmp
USER 10001:10001
ENTRYPOINT ["python", "/app/worker.py"]
