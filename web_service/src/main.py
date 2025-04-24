import os
import pickle
import queue
import json
import threading
import time
from flask import Flask, Response
import sys
sys.path.append('/app/src')
from shared.ProcessItem import ProcessItem, StatusProgressBar
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
connected_clients = 0  # Zähler für verbundene Clients


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
        global connected_clients
        logger.warning(f"Connected clients: {connected_clients}")
        if connected_clients > 0:  # Nur wenn Clients verbunden sindd
            item: ProcessItem = pickle.loads(body)
            payload = dict(
                id=item.db_id,
                file_name=item.filename,
                file_status=item.status.value,
                local_filepath=item.local_directory_above,
                previewimage_path=item.preview_image_path,
                remote_filepath=item.remote_file_path,
                pdf_pages=int(item.pdf_pages) if item.pdf_pages is not None else 0,
                status_progressbar=int(StatusProgressBar.get_progress(item.status)),
                web_url=item.web_url,
            )
            payload["dashboard_data"] = get_dashboard_info()  # Nur bei Bedarf abrufen
            sse_queue.put(json.dumps(payload, default=str))  # Ensure all objects are serializable
            logger.debug(f"Received update from RabbitMQ: {payload}")
        else:
            logger.debug("No connected clients. Skipping SSE queue update.")

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
    global connected_clients

    def event_stream():
        global connected_clients
        connected_clients += 1
        logger.info(f"Client connected. Total connected clients: {connected_clients}")
        try:
            while True:
                try:
                    data = sse_queue.get(timeout=10)
                    logger.debug(f"Data retrieved from SSE queue: {data}")
                    time.sleep(0.2)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            connected_clients -= 1
            logger.info(f"Client disconnected. Total connected clients: {connected_clients}")

    return Response(event_stream(), mimetype="text/event-stream")


start_rabbitmq_listener()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
    logger.info("Web service started.")
