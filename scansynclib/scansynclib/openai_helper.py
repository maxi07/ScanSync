from openai import OpenAI, AuthenticationError, RateLimitError
from scansynclib.ProcessItem import FileNamingStatus, ProcessItem
from scansynclib.logging import logger
from tenacity import Retrying, RetryError, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from scansynclib.helpers import validate_smb_filename, extract_text
from scansynclib.sqlite_wrapper import execute_query
from scansynclib.settings import settings


OPENAI_MODEL = "gpt-4.1-nano"
TOKEN_FILE = '/app/data/token_openai.json'
USER_PROFILE_FILE = '/app/data/user_profile_openai.json'
USER_IMAGE_FILE = '/app/data/user_image_openai.jpeg'


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
            input="Please respond with the words 'it works'",
        )
        if response.output_text.lower() == "it works":
            logger.info("OppenAI key is valid")
            return 200, "OpenAI key is valid"
        else:
            logger.warning(f"OpenAI key worked, but did not return expected result. Result is: {response.output_text}")
            return 200, "OpenAI key worked, but something was off"
    except AuthenticationError:
        return 401, "OpenAI key is invalid or wrong permissions set."
    except RateLimitError:
        return 429, "OpenAI rate limit reached! Either not enough credits or too many requests."
    except Exception as e:
        logger.exception(f"An error occurred while testing OpenAI key: {e}")
        return 400, "An error occurred while testing OpenAI key"


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
    execute_query(
        "UPDATE file_naming_jobs SET file_naming_status = ?, model = ?, method = ? WHERE id = ?",
        (FileNamingStatus.PROCESSING.name, OPENAI_MODEL, "openai", item.file_naming_db_id)
    )
    if not item.ocr_file:
        logger.warning("No OCR file found. Using default filename.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.NO_OCR_FILE.name, FileNamingStatus.NO_OCR_FILE.value, item.file_naming_db_id)
        )
        return item.filename_without_extension

    # Get PDF Text
    pdf_text = extract_text(item.ocr_file)

    if not pdf_text:
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
        retry_strategy = Retrying(
            stop=stop_after_attempt(3),
            wait=wait_random_exponential(multiplier=10, min=10, max=30),
            retry=retry_if_exception_type(RateLimitError),
            after=lambda retry_state: logger.warning(
                f"Attempt nr {retry_state.attempt_number} failed with exception: {retry_state.outcome.exception()}, waited {round(retry_state.upcoming_sleep, 1)} seconds"
            ),
        )
        for attempt in retry_strategy:
            with attempt:
                openai_filename = client.responses.create(
                    model=OPENAI_MODEL,
                    instructions="Identify a suitable filename for the following pdf content. Keep the language of the file name in the original language and do not add any other language. Make the filename safe for SMB. Do not add a file extension. Separate words with a underscore. Have a maximum filename length of 30 characters. Only return the filename without any additional text.",
                    input=pdf_text,
                )
        if openai_filename:
            logger.debug(f"Received OpenAI filename: {openai_filename.output_text}")
            sanitized_filename = validate_smb_filename(openai_filename.output_text)
            logger.debug(f"Sanitized OpenAI filename: {sanitized_filename}")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, success = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.COMPLETED.name, True, item.file_naming_db_id)
            )
            return sanitized_filename
        else:
            logger.warning("OpenAI key worked, but did not return any result.")
            execute_query(
                "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
                (FileNamingStatus.FAILED.name, "OpenAI key worked, but did not return any result.", item.file_naming_db_id)
            )
            return item.filename_without_extension
    except AuthenticationError:
        logger.warning("OpenAI key is invalid or wrong permissions set.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.AUTHENTICATION_ERROR.name, "OpenAI key is invalid or wrong permissions set.", item.file_naming_db_id)
        )
        return item.filename_without_extension
    except RetryError as retryerr:
        logger.warning(f"OpenAI rate limit reached! Either not enough credits or too many requests. Tried {retryerr.last_attempt.attempt_number} times.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.RATE_LIMIT_ERROR.name, f"OpenAI rate limit reached! Either not enough credits or too many requests. Tried {retryerr.last_attempt.attempt_number} times.", item.file_naming_db_id)
        )
        return item.filename_without_extension
    except Exception as ex:
        logger.exception("An error occurred while creating a file name.")
        execute_query(
            "UPDATE file_naming_jobs SET file_naming_status = ?, error_description = ?, finished = DATETIME('now', 'localtime') WHERE id = ?",
            (FileNamingStatus.FAILED.name, str(ex), item.file_naming_db_id)
        )
        return item.filename_without_extension
    finally:
        # Close the OpenAI client connection
        client.close()
