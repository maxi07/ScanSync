FROM python:3.13-slim

EXPOSE 5001

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser

WORKDIR /app

# tzdata for setting timezone
ENV TZ=Europe/Berlin

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 && rm -rf /var/lib/apt/lists/*
RUN python -m pip install -r requirements.txt
COPY . /app
RUN chown -R appuser /app
USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:5001", "src.main:app"]