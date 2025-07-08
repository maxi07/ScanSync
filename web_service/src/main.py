import os
import pickle
import queue
import json
import threading
import time
from flask import Flask, Response, request, send_from_directory
import sys
sys.path.append('/app/src')
from scansynclib.ProcessItem import ProcessItem, StatusProgressBar
from scansynclib.helpers import connect_rabbitmq, format_time_difference
from scansynclib.logging import logger
from routes.dashboard import dashboard_bp
from routes.sync import sync_bp
from routes.settings import settings_bp
from routes.api import api_bp
from routes.onedrive import onedrive_bp
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.config import config

logger.info("Starting web service...")

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.register_blueprint(dashboard_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(api_bp)
app.register_blueprint(onedrive_bp)

sse_queue = queue.Queue()
connected_clients = 0


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
        if connected_clients > 0:
            item: ProcessItem = pickle.loads(body)
            payload = dict(
                id=item.db_id,
                file_name=item.filename,
                file_status=item.status.value,
                local_filepath=item.local_directory_above,
                previewimage_path=item.preview_image_path,
                remote_filepath=item.OneDriveDestinations[0].remote_file_path if item.OneDriveDestinations else None,
                pdf_pages=int(item.pdf_pages) if item.pdf_pages is not None else 0,
                status_progressbar=int(StatusProgressBar.get_progress(item.status)),
                web_url=item.web_url,
                smb_target_ids=item.smb_target_ids,
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
            SELECT *,
                (SELECT COUNT(*) FROM scanneddata WHERE status_code = 5) AS processed_pdfs,
                (SELECT COUNT(*) FROM scanneddata WHERE status_code BETWEEN 0 AND 4) AS processing_pdfs,
                (SELECT DATETIME(modified) FROM scanneddata ORDER BY modified DESC LIMIT 1) AS latest_processing,
                (SELECT DATETIME(modified) FROM scanneddata WHERE status_code = 5 ORDER BY modified DESC LIMIT 1) AS latest_completed
            FROM scanneddata
            ORDER BY created DESC, id DESC
        """
        result = execute_query(query, fetchone=True)
        processed_pdfs = result.get('processed_pdfs', 0)
        processing_pdfs = result.get('processing_pdfs', 0)
        latest_timestamp_processing = result.get('latest_processing', None)
        latest_timestamp_completed = result.get('latest_completed', "Never")
        if not latest_timestamp_processing:
            latest_timestamp_processing = latest_timestamp_completed

        # Convert timestamps into strings for web
        if latest_timestamp_processing:
            latest_timestamp_processing = "Updated " + format_time_difference(latest_timestamp_processing)
        else:
            latest_timestamp_processing = "Never"

        if latest_timestamp_completed:
            latest_timestamp_completed = "Updated " + format_time_difference(latest_timestamp_completed)
        else:
            latest_timestamp_completed = "Never"

        logger.debug(f"Dashboard data fetched: {result}")

        return dict(
            processed_pdfs=processed_pdfs,
            processing_pdfs=processing_pdfs,
            latest_timestamp_processing_timestamp=latest_timestamp_processing,
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
            r"SELECT COUNT(*) AS count FROM scanneddata WHERE status_code < 0 AND LOWER(file_status) NOT LIKE '%deleted%'",
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
        global connected_clients
        connected_clients += 1
        logger.info(f"Client connected. Total connected clients: {connected_clients}")
        try:
            yield 'data: {"status": "connected"}\n\n'
            while True:
                try:
                    data = sse_queue.get(timeout=2)
                    logger.debug(f"Data retrieved from SSE queue: {data}")
                    time.sleep(0.2)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            connected_clients -= 1
            logger.info(f"Client disconnected. Total connected clients: {connected_clients}")

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/favicon.ico")
def favicon():
    """Serve the favicon."""
    prefers_dark = 'dark' in request.headers.get('User-Agent', '').lower()
    favicon_file = 'ScanSync_logo_black.ico' if prefers_dark else 'ScanSync_logo_white.ico'
    return send_from_directory(os.path.join(app.root_path, 'static/images'), favicon_file, mimetype="image/x-icon")


start_rabbitmq_listener()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
    logger.info("Web service started.")
