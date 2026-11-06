FROM python:3.13-slim-trixie

WORKDIR /app
ENV TZ=Europe/Berlin
ENV CONFIG_PATH=/app/scansynclib/scansynclib/config.json
COPY file_naming_service/requirements.txt .
COPY requirements-dev.txt /tmp/constraints.txt
COPY scansynclib/ /app/scansynclib/
RUN --mount=type=cache,target=/root/.cache/pip pip install -c /tmp/constraints.txt -r requirements.txt /app/scansynclib && pip check
COPY file_naming_service/ /app/

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

CMD ["python", "main.py"]