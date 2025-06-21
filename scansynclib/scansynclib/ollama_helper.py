import requests
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_random_exponential
import urllib3
from scansynclib.ollama_settings import ollama_settings
from scansynclib.ProcessItem import FileNamingStatus, ProcessItem
from scansynclib.helpers import extract_text
from scansynclib.logging import logger
from scansynclib.sqlite_wrapper import execute_query


def test_ollama_server(server_url, server_port, model):
    try:
        url = f"{server_url}:{server_port}"
        logger.info(f"Testing Ollama server at {url} with model {model}")
        response = requests.get(url)
        if response.status_code != 200 or "Ollama is running" not in response.text:
            logger.error(f"Failed to reach Ollama server: {response.status_code} - {response.text}")    
            return False, f"Failed to reach Ollama server: {response.status_code} - {response.text}"
        logger.info("Ollama server is reachable")

        model_url = f"{url}/api/generate"
        model_response = requests.post(model_url, json={"model": model, "stream": False, "prompt": "Please respond with 'it works'."})
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

    execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, model = ?, method = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.PROCESSING.name, ollama_settings.model, "ollama", item.file_naming_db_id)
        )

    if not item.ocr_file:
        logger.warning("No OCR file found. Using default filename.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_OCR_FILE.name, item.file_naming_db_id)
        )
        return item.filename_without_extension

    # Get PDF Text
    pdf_text = extract_text(item.ocr_file)

    if not pdf_text:
        logger.warning("Failed to extract text from PDF. Using default filename.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_PDF_TEXT.name, item.file_naming_db_id)
        )
        return item.filename_without_extension

    # Send text to Ollama for filename generation
    try:
        url = f"{ollama_settings.server_url}:{ollama_settings.server_port}/api/generate"
        system_prompt = (
            "Identify a suitable filename for the following pdf content. "
            "Keep the language of the file name in the original language and do not mix languages. "
            "Make the filename safe for SMB. Do not add a file extension. "
            "Separate words with a underscore, replace spaces with underscores. "
            "Have a maximum filename length of 30 characters."
        )
        payload = {
            "model": ollama_settings.model,
            "system": system_prompt,
            "prompt": pdf_text,
            "stream": False
        }
        headers = {"Content-Type": "application/json"}
        response = post_to_ollama(payload, headers)
        logger.debug(f"Ollama response status code: {response.status_code}, response text: {response.text}")
        if response.status_code == 200:
            new_filename = response.json().get('response', '').strip()
            if new_filename:
                logger.info(f"Extracted filename from Ollama response: {new_filename}")
                execute_query(
                    "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                    (FileNamingStatus.COMPLETED.name, item.file_naming_db_id)
                )
                return new_filename
        elif response.status_code == 404:
            # Handle 404 error specifically as it indicates the model was not found but also Page not found
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                try:
                    error_info = response.json()
                    logger.error(f"Ollama model {ollama_settings.model} not found on the server: {error_info}")
                    execute_query(
                        "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                        (FileNamingStatus.MODEL_NOT_FOUND.name, item.file_naming_db_id)
                    )
                except Exception as e:
                    logger.error(f"Failed to parse error response from Ollama: {str(e)}")
                    execute_query(
                        "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                        (FileNamingStatus.MODEL_NOT_FOUND.name, item.file_naming_db_id)
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
            logger.warning("Ollama did not return a valid filename. Using default.")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, response.text, item.file_naming_db_id)
            )
            return item.filename_without_extension
    except RetryError as retryerr:
        logger.error(f"Error connecting to Ollama server: {str(retryerr)}")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_SERVER_CONNECTION.name, item.file_naming_db_id)
        )
        return item.filename_without_extension


@retry(stop=stop_after_attempt(3),
       wait=wait_random_exponential(multiplier=1, min=2, max=10),
       retry=retry_if_exception(is_retryable_exception))
def post_to_ollama(payload, headers):
    url = f"{ollama_settings.server_url}:{ollama_settings.server_port}/api/generate"
    return requests.post(url, json=payload, headers=headers, timeout=120)
