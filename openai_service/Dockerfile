FROM python:3.13.3-slim

WORKDIR /app
ENV TZ=Europe/Berlin
ENV CONFIG_PATH=/app/scansynclib/scansynclib/config.json
COPY openai_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY openai_service/ /app/
COPY scansynclib/ /app/scansynclib/
RUN pip install /app/scansynclib

CMD ["python", "main.py"]