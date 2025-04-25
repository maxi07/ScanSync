FROM python:3.13-slim

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
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN python -m pip install -r requirements.txt
COPY web_service/ /app
COPY scansynclib/ /app/scansynclib/
COPY web_service/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN pip install /app/scansynclib
RUN test -d /app/scansynclib || (echo "scansynclib missing!" && exit 1)
USER root

ENTRYPOINT ["/entrypoint.sh"]