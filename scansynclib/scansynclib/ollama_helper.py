import requests
import time
from scansynclib.analytics import elapsed_ms, track
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_random_exponential
import urllib3
from scansynclib.ProcessItem import FileNamingStatus, ProcessItem
from scansynclib.helpers import extract_text, validate_smb_filename
from scansynclib.logging import logger
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.settings import settings


def test_ollama_server(server_url, server_port, model):
    try:
        url = f"{server_url}:{server_port}"
        logger.info(f"Testing Ollama server at {url} with model {model}")
        response = requests.get(url, timeout=10)
        if response.status_code != 200 or "Ollama is running" not in response.text:
            logger.error(f"Failed to reach Ollama server: {response.status_code} - {response.text}")
            return False, f"Failed to reach Ollama server: {response.status_code} - {response.text}"
        logger.info("Ollama server is reachable")

        model_url = f"{url}/api/generate"
        model_response = requests.post(
            model_url,
            json={"model": model, "stream": False, "think": False, "options": {"num_predict": 128}, "prompt": "Please respond with 'it works'."},
            timeout=120,
        )
        if model_response.status_code == 200:
            logger.info(f"Model {model} is available on the Ollama server")
            return True, "Ollama server and model are reachable"
        else:
            logger.error(f"Model {model} not found on the Ollama server: {model_response.status_code} - {model_response.text}")
            return False, f"Model {model} not found on the Ollama server: {model_response.status_code} - {model_response.text}"
    except requests.RequestException as e:
        logger.error(f"Error connecting to Ollama server: {str(e)}")
        return False, f"Error connecting to Ollama server: {str(e)}"
    except Exception as e:
        logger.exception(f"Unexpected error while testing Ollama server: {str(e)}")
        return False, f"Unexpected error while testing Ollama server: {str(e)}"


def is_retryable_exception(e):
    def has_retryable_cause(exc):
        while exc:
            if isinstance(exc, OSError) and getattr(exc, 'errno', None) == 101:
                return True
            if isinstance(exc, (
                requests.exceptions.RequestException,
                urllib3.exceptions.HTTPError,
                urllib3.exceptions.MaxRetryError,
                urllib3.exceptions.TimeoutError,
                urllib3.exceptions.ConnectionError,
                OSError
            )):
                return True
            exc = exc.__cause__ or exc.__context__
        return False

    return has_retryable_cause(e)


def generate_filename_ollama(item: ProcessItem) -> str:
    """
    Generates a filename for a PDF based on its content using Ollama.

    Tries to extract the text from the PDF. If Ollama is configured, sends the text to Ollama to generate a filename.
    Otherwise, just returns the original filename.

    Parameters:
    - item (ProcessItem): The ProcessItem containing the OCR file and metadata.

    Returns:
    - str: The generated filename if successful, otherwise the original filename without extension.
    """
    logger.info(f"Generating filename using Ollama for {item.filename}")
    started = time.monotonic()
    telemetry = {"item": item, "provider": "ollama", "model": settings.file_naming.ollama_model}
    item.analytics_naming_retries = 0
    track("naming.started", **telemetry)

    execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, model = ?, method = ? WHERE id = ?",
            (FileNamingStatus.PROCESSING.name, settings.file_naming.ollama_model, "ollama", item.file_naming_db_id)
        )

    if not item.ocr_file:
        track("naming.skipped", **telemetry, reason="no_ocr_file", fallback_used=True, duration_ms=elapsed_ms(started))
        logger.warning("No OCR file found. Using default filename.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_OCR_FILE.name, FileNamingStatus.NO_OCR_FILE.value, item.file_naming_db_id)
        )
        return item.filename_without_extension

    # Get PDF Text
    pdf_text = extract_text(item.ocr_file)

    if not pdf_text:
        track("naming.skipped", **telemetry, reason="no_pdf_text", fallback_used=True, duration_ms=elapsed_ms(started))
        logger.warning("Failed to extract text from PDF. Using default filename.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_PDF_TEXT.name, FileNamingStatus.NO_PDF_TEXT.value, item.file_naming_db_id)
        )
        return item.filename_without_extension

    # Send text to Ollama for filename generation
    try:
        system_prompt = (
            "You are a filename generator. "
            "Given the content of a PDF, respond with a single, suitable filename only. "
            "Do not include any explanations or additional text. "
            "Do not use quotation marks. "
            "Do not add a file extension. "
            "The filename must be in the original language of the content. "
            "Do not mix languages. "
            "Make the filename safe for SMB: no special characters, only use letters, numbers, and underscores. "
            "Replace all spaces with underscores. "
            "Seperate words using underscores, do not use spaces. "
            "Maximum filename length is 30 characters. "
            "Return only the filename – nothing else, also no notes."
        )
        payload = {
            "model": settings.file_naming.ollama_model,
            "system": system_prompt,
            "prompt": pdf_text,
            "stream": False,
            "think": False,
            "options": {"num_predict": 128},
        }
        headers = {"Content-Type": "application/json"}
        response = post_to_ollama(payload, headers, item=item)
        logger.debug(f"Ollama response status code: {response.status_code}, response text: {response.text}")
        if response.status_code == 200:
            new_filename = response.json().get('response', '').strip()
            if new_filename:
                logger.info(f"Extracted filename from Ollama response: {new_filename}")
                sanitized_filename = validate_smb_filename(new_filename)[:30].rstrip(" ._")
                logger.debug(f"Sanitized Ollama filename: {sanitized_filename}")
                execute_query(
                    "UPDATE file_naming_jobs SET file_naming_status = ?, success = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                    (FileNamingStatus.COMPLETED.name, True, item.file_naming_db_id)
                )
                track("naming.completed", **telemetry, duration_ms=elapsed_ms(started), fallback_used=False, retries=item.analytics_naming_retries)
                return sanitized_filename
            logger.warning("Ollama returned an empty filename. Using default filename.")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, "Ollama returned an empty filename.", item.file_naming_db_id)
            )
            track("naming.failed", **telemetry, reason="empty_response", status_code=200, duration_ms=elapsed_ms(started), fallback_used=True)
            return item.filename_without_extension
        elif response.status_code == 404:
            track("naming.failed", **telemetry, reason="model_not_found", status_code=404, duration_ms=elapsed_ms(started), fallback_used=True)
            # Handle 404 error specifically as it indicates the model was not found but also Page not found
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                try:
                    error_info = response.json()
                    logger.error(f"Ollama model {settings.file_naming.ollama_model} not found on the server: {error_info}")
                    execute_query(
                        "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                        (FileNamingStatus.MODEL_NOT_FOUND.name, FileNamingStatus.MODEL_NOT_FOUND.value, item.file_naming_db_id)
                    )
                except Exception as e:
                    logger.error(f"Failed to parse error response from Ollama: {str(e)}")
                    execute_query(
                        "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                        (FileNamingStatus.MODEL_NOT_FOUND.name, FileNamingStatus.MODEL_NOT_FOUND.value, item.file_naming_db_id)
                    )
                finally:
                    return item.filename_without_extension
            else:
                logger.error(f"Ollama server returned a 404 error without JSON content: {response.text}. Is Ollama running?")
                execute_query(
                    "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                    (FileNamingStatus.FAILED.name, response.text, item.file_naming_db_id)
                )
            return item.filename_without_extension
        else:
            track("naming.failed", **telemetry, reason="http_error", status_code=response.status_code, duration_ms=elapsed_ms(started), fallback_used=True)
            logger.warning("Ollama did not return a valid filename. Using default.")
            error_info = ""
            try:
                error_info = response.json()
                logger.error(f"Ollama server returned an error: {error_info.get('error', 'Unknown error')}")
            except Exception:
                pass
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, error_info if error_info else response.text, item.file_naming_db_id)
            )
            return item.filename_without_extension
    except RetryError as retryerr:
        track("naming.failed", **telemetry, error=retryerr.last_attempt.exception(), duration_ms=elapsed_ms(started), fallback_used=True, retries=retryerr.last_attempt.attempt_number - 1)
        logger.error(f"Error connecting to Ollama server: {str(retryerr)}")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_SERVER_CONNECTION.name, FileNamingStatus.NO_SERVER_CONNECTION.value, item.file_naming_db_id)
        )
        return item.filename_without_extension
    except Exception as error:
        track("naming.failed", **telemetry, error=error, duration_ms=elapsed_ms(started), fallback_used=True)
        raise


def log_ollama_retry(retry_state):
    item = retry_state.kwargs.get("item")
    if item is not None:
        item.analytics_naming_retries = retry_state.attempt_number
    track(
        "naming.retried", item=item, provider="ollama", model=settings.file_naming.ollama_model,
        error=retry_state.outcome.exception(), attempt=retry_state.attempt_number,
    )
    logger.warning(
        "Ollama request attempt %s/3 failed: %s. Retrying in %.1f seconds.",
        retry_state.attempt_number,
        retry_state.outcome.exception(),
        retry_state.next_action.sleep,
    )


@retry(stop=stop_after_attempt(3),
       wait=wait_random_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_exception(is_retryable_exception),
       before_sleep=log_ollama_retry)
def post_to_ollama(payload, headers, item=None):
    url = f"{settings.file_naming.ollama_server_url}:{settings.file_naming.ollama_server_port}/api/generate"
    logger.info("Sending Ollama request to %s using model %s (timeout: 120 seconds).", url, payload.get("model"))
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    logger.info("Received Ollama response: HTTP %s.", response.status_code)
    return response
