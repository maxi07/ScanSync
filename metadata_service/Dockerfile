FROM python:3.13-slim

WORKDIR /app
ENV TZ=Europe/Berlin
ENV CONFIG_PATH=/app/scansynclib/scansynclib/config.json
COPY metadata_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY metadata_service/ /app
COPY scansynclib/ /app/scansynclib/
RUN pip install /app/scansynclib

CMD ["python", "main.py"]