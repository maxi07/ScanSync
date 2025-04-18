import os
import queue
import json
import threading
import time
from flask import Flask, Response
import sys
sys.path.append('/app/src')
from shared.helpers import connect_rabbitmq, format_time_difference
from shared.logging import logger
from routes.dashboard import dashboard_bp
from routes.sync import sync_bp
from routes.settings import settings_bp
from routes.api import api_bp
from routes.onedrive import onedrive_bp
from shared.sqlite_wrapper import execute_query
from shared.config import config


logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(api_bp)
app.register_blueprint(onedrive_bp)

sse_queue = queue.Queue()


def start_rabbitmq_listener():
    logger.info("Spawning RabbitMQ listener thread.")
    t = threading.Thread(target=rabbitmq_listener, daemon=True)
    t.start()


def rabbitmq_listener():
    logger.info("Started RabbitMQ listener thread.")

    connection, channel = connect_rabbitmq()

    # Use fanout as exchange type to broadcast messages to all connected clients
    exchange_name = "sse_updates_fanout"
    channel.exchange_declare(exchange=exchange_name, exchange_type='fanout')
    result = channel.queue_declare(queue='', exclusive=True)
    queue_name = result.method.queue

    channel.queue_bind(exchange=exchange_name, queue=queue_name)

    def callback(ch, method, properties, body):
        payload = json.loads(body.decode())
        payload["dashboard_data"] = get_dashboard_info()
        sse_queue.put(json.dumps(payload))  # an verbundene Clients senden
        logger.debug(f"Received update from RabbitMQ: {payload}")

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
    channel.start_consuming()


def get_dashboard_info() -> dict:
    """Fetch dashboard information from the database using a single query."""
    try:
        query = """
            SELECT
                (SELECT COUNT(*) FROM scanneddata WHERE file_status = "Completed") AS completed_count,
                (SELECT COUNT(*) FROM scanneddata WHERE LOWER(file_status) LIKE "pending") AS pending_count,
                (SELECT DATETIME(created, "localtime") FROM scanneddata 
                 WHERE file_status = "Pending" 
                 ORDER BY created DESC LIMIT 1) AS latest_pending_timestamp,
                (SELECT DATETIME(modified, "localtime") FROM scanneddata 
                 WHERE file_status = "Completed" 
                 ORDER BY modified DESC LIMIT 1) AS latest_completed_timestamp
        """
        result = execute_query(query, fetchone=True)

        processed_pdfs = result.get('completed_count', 0)
        pending_pdfs = result.get('pending_count', 0)
        latest_timestamp_pending = result.get('latest_pending_timestamp', None)
        latest_timestamp_completed = result.get('latest_completed_timestamp', "Never")
        if not latest_timestamp_pending:
            latest_timestamp_pending = latest_timestamp_completed

        # Convert timestamps into strings for web
        if latest_timestamp_pending:
            latest_timestamp_pending = "Updated " + format_time_difference(latest_timestamp_pending)
        else:
            latest_timestamp_pending = "Never"

        if latest_timestamp_completed:
            latest_timestamp_completed = "Updated " + format_time_difference(latest_timestamp_completed)
        else:
            latest_timestamp_completed = "Never"

        logger.debug(f"Dashboard data fetched: {result}")

        return dict(
            processed_pdfs=processed_pdfs,
            pending_pdfs=pending_pdfs,
            pending_pdfs_latest_timestamp=latest_timestamp_pending,
            processed_pdfs_latest_timestamp=latest_timestamp_completed
        )
    except Exception:
        logger.exception("Failed fetching dashboard information.")
        return dict(
            completed_count="Unknown",
            pending_count="Unknown",
            latest_pending_timestamp="Unknown",
            latest_completed_timestamp="Unknown"
        )


@app.context_processor
def inject_config():
    """Inject config values into templates."""
    try:
        failed_document_count = execute_query(
            r"SELECT COUNT(*) AS count FROM scanneddata WHERE LOWER(file_status) LIKE '%failed%'",
            fetchone=True
        ).get('count', 0)
    except Exception:
        logger.exception("Failed counting failed documents.")
        failed_document_count = 0

    return dict(
        failed_document_count=failed_document_count,
        version=config.get("version", "Unknown"),
    )


@app.route("/stream")
def stream():
    def event_stream():
        while True:
            try:
                data = sse_queue.get(timeout=10)
                logger.debug(f"Data retrieved from SSE queue: {data}")
                time.sleep(0.2)
                yield f"data: {data}\n\n"
            except queue.Empty:
                yield ": keep-alive\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


start_rabbitmq_listener()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
    logger.info("Web service started.")
