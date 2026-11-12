FROM python:3.15-slim-trixie

EXPOSE 5001

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

# tzdata for setting timezone
ENV TZ=Europe/Berlin
ENV CONFIG_PATH=/app/scansynclib/scansynclib/config.json
COPY web_service/requirements.txt .
COPY requirements-dev.txt /tmp/constraints.txt
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 gosu && rm -rf /var/lib/apt/lists/*
COPY scansynclib/ /app/scansynclib/
RUN --mount=type=cache,target=/root/.cache/pip pip install -c /tmp/constraints.txt -r requirements.txt /app/scansynclib && pip check
COPY web_service/ /app
COPY web_service/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /app
RUN test -d /app/scansynclib || (echo "scansynclib missing!" && exit 1)
USER root

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
ENTRYPOINT ["/entrypoint.sh"]