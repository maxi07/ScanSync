FROM python:3.13.3-slim

WORKDIR /app
ENV TZ=Europe/Berlin
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "main.py"]