from openai import OpenAI, APIStatusError, AuthenticationError, RateLimitError
import time
from scansynclib.analytics import elapsed_ms, track
from scansynclib.ProcessItem import FileNamingStatus, ProcessItem
from scansynclib.logging import logger
from tenacity import Retrying, RetryError, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from scansynclib.helpers import validate_smb_filename, extract_text
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.settings import settings


OPENAI_MODEL = "gpt-6-luna"
MAX_FILENAME_LENGTH = 30
TOKEN_FILE = '/app/data/token_openai.json'
USER_PROFILE_FILE = '/app/data/user_profile_openai.json'
USER_IMAGE_FILE = '/app/data/user_image_openai.jpeg'


def format_api_error(error: APIStatusError) -> str:
    body = error.body if isinstance(error.body, dict) else {}
    details = body.get("error", body)
    if not isinstance(details, dict):
        details = {}
    message = details.get("message")
    if not isinstance(message, str):
        message = ""
    code = details.get("code")
    if error.status_code == 404:
        if any(term in message.lower() for term in ("deprecated", "retired", "shut down")):
            summary = f"OpenAI model is deprecated: {OPENAI_MODEL}."
        else:
            summary = f"OpenAI model not found or inaccessible: {OPENAI_MODEL}."
    else:
        summary = "OpenAI request failed."
    status = f"HTTP {error.status_code}"
    if isinstance(code, str) and code:
        status += f"; {code}"
    return f"{summary} ({status}) {message}".strip()


def test_key(key) -> tuple[int, str]:
    """
    Tests if an OpenAI API key is valid, adds it to the environment if so,
    and returns a status code indicating whether it was valid.

    Parameters:
    - key (str): The OpenAI API key to test.

    Returns:
    - int: Status code indicating the result of the test
    - str: Status message
    """
    client = OpenAI(
        api_key=key,
    )

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            reasoning={"effort": "none"},
            input="Please respond with the words 'it works'",
        )
        if response.output_text.lower() == "it works":
            logger.info("OpenAI key is valid")
            return 200, "OpenAI key is valid"
        else:
            logger.warning(f"OpenAI key worked, but did not return expected result. Result is: {response.output_text}")
            return 200, "OpenAI key worked, but something was off"
    except AuthenticationError as error:
        track("dependency.failed", error=error, provider="openai", model=OPENAI_MODEL, operation="key_test")
        return 401, "OpenAI key is invalid or wrong permissions set."
    except RateLimitError as error:
        track("dependency.failed", error=error, provider="openai", model=OPENAI_MODEL, operation="key_test")
        return 429, "OpenAI rate limit reached! Either not enough credits or too many requests."
    except APIStatusError as error:
        track("dependency.failed", error=error, provider="openai", model=OPENAI_MODEL, operation="key_test")
        return error.status_code, format_api_error(error)
    except Exception as e:
        logger.exception(f"An error occurred while testing OpenAI key: {e}")
        return 400, "An error occurred while testing OpenAI key"
    finally:
        client.close()


def generate_filename_openai(item: ProcessItem) -> str:
    """
    Generates a filename for a PDF based on its content using OpenAI.

    Tries to extract the text from the PDF. If OpenAI is configured, sends the text to OpenAI to generate a filename.
    Otherwise, just returns the original filename.

    Parameters:
    - pdf_path (str): The path to the PDF file.

    Returns:
    - str: The generated filename if successful, otherwise the original filename without extension.
    """
    logger.info(f"Generating filename using OpenAI for {item.filename}")
    started = time.monotonic()
    telemetry = {"item": item, "provider": "openai", "model": OPENAI_MODEL}
    track("naming.started", **telemetry)
    execute_query(
        "UPDATE file_naming_jobs SET file_naming_status = ?, model = ?, method = ? WHERE id = ?",
        (FileNamingStatus.PROCESSING.name, OPENAI_MODEL, "openai", item.file_naming_db_id)
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

    client = OpenAI(
        api_key=settings.file_naming.openai_api_key,
    )

    try:
        # Retry logic for OpenAI API calls
        def log_retry(retry_state):
            logger.warning("OpenAI request attempt %s failed; retrying.", retry_state.attempt_number)
            track("naming.retried", **telemetry, error=retry_state.outcome.exception(), attempt=retry_state.attempt_number)

        retry_strategy = Retrying(
            stop=stop_after_attempt(3),
            wait=wait_random_exponential(multiplier=10, min=10, max=30),
            retry=retry_if_exception_type(RateLimitError),
            before_sleep=log_retry,
        )
        for attempt in retry_strategy:
            with attempt:
                openai_filename = client.responses.create(
                    model=OPENAI_MODEL,
                    reasoning={"effort": "none"},
                    instructions="Identify a suitable filename for the following pdf content. Keep the language of the file name in the original language and do not add any other language. Make the filename safe for SMB. Do not add a file extension. Separate words with a underscore. Have a maximum filename length of 30 characters. Only return the filename without any additional text.",
                    input=pdf_text,
                )
        if openai_filename and openai_filename.output_text.strip():
            logger.debug(f"Received OpenAI filename: {openai_filename.output_text}")
            sanitized_filename = validate_smb_filename(openai_filename.output_text)[:MAX_FILENAME_LENGTH].rstrip(" ._")
            logger.debug(f"Sanitized OpenAI filename: {sanitized_filename}")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, success = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.COMPLETED.name, True, item.file_naming_db_id)
            )
            track("naming.completed", **telemetry, duration_ms=elapsed_ms(started), fallback_used=False, retries=attempt.retry_state.attempt_number - 1)
            return sanitized_filename
        else:
            logger.warning("OpenAI key worked, but did not return any result.")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, "OpenAI key worked, but did not return any result.", item.file_naming_db_id)
            )
            track("naming.failed", **telemetry, reason="empty_response", duration_ms=elapsed_ms(started), fallback_used=True)
            return item.filename_without_extension
    except AuthenticationError as error:
        track("naming.failed", **telemetry, error=error, duration_ms=elapsed_ms(started), fallback_used=True)
        logger.warning("OpenAI key is invalid or wrong permissions set.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.AUTHENTICATION_ERROR.name, "OpenAI key is invalid or wrong permissions set.", item.file_naming_db_id)
        )
        return item.filename_without_extension
    except RetryError as retryerr:
        track("naming.failed", **telemetry, error=retryerr.last_attempt.exception(), duration_ms=elapsed_ms(started), fallback_used=True, retries=retryerr.last_attempt.attempt_number - 1)
        logger.warning(f"OpenAI rate limit reached! Either not enough credits or too many requests. Tried {retryerr.last_attempt.attempt_number} times.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.RATE_LIMIT_ERROR.name, f"OpenAI rate limit reached! Either not enough credits or too many requests. Tried {retryerr.last_attempt.attempt_number} times.", item.file_naming_db_id)
        )
        return item.filename_without_extension
    except APIStatusError as error:
        track("naming.failed", **telemetry, error=error, duration_ms=elapsed_ms(started), fallback_used=True)
        description = format_api_error(error)
        status = FileNamingStatus.MODEL_NOT_FOUND if error.status_code == 404 else FileNamingStatus.FAILED
        logger.warning(description)
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (status.name, description, item.file_naming_db_id)
        )
        return item.filename_without_extension
    except Exception as ex:
        track("naming.failed", **telemetry, error=ex, duration_ms=elapsed_ms(started), fallback_used=True)
        logger.exception("An error occurred while creating a file name.", extra={"analytics_handled": True})
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.FAILED.name, str(ex), item.file_naming_db_id)
        )
        return item.filename_without_extension
    finally:
        # Close the OpenAI client connection
        client.close()
