from openai import OpenAI, AuthenticationError, RateLimitError
from shared.ProcessItem import ProcessItem
from shared.logging import logger
from pypdf import PdfReader
from shared.openai_settings import openai_settings
import re
from tenacity import Retrying, RetryError, stop_after_attempt, wait_random_exponential, retry_if_exception_type


OPENAI_MODEL = "gpt-4.1-nano"
TOKEN_FILE = '/app/data/token_openai.json'
USER_PROFILE_FILE = '/app/data/user_profile_openai.json'
USER_IMAGE_FILE = '/app/data/user_image_openai.jpeg'


def test_and_add_key(key) -> tuple[int, str]:
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
            openai_settings.api_key = key
            openai_settings.save()
            return 200, "OpenAI key is valid"
        else:
            logger.warning(f"OpenAI key worked, but did not return expected result. Result is: {response.output_text}")
            openai_settings.api_key = key
            openai_settings.save()
            return 200, "OpenAI key worked, but something was off"
    except AuthenticationError:
        return 401, "OpenAI key is invalid or wrong permissions set."
    except RateLimitError:
        return 429, "OpenAI rate limit reached! Either not enough credits or too many requests."
    except Exception as e:
        logger.exception(f"An error occurred while testing OpenAI key: {e}")
        return 400, "An error occurred while testing OpenAI key"


def generate_filename(item: ProcessItem) -> str:
    """
    Generates a filename for a PDF based on its content using OpenAI.

    Tries to extract the text from the PDF. If OpenAI is configured, sends the text to OpenAI to generate a filename.
    Otherwise, just returns the original filename.

    Parameters:
    - pdf_path (str): The path to the PDF file.

    Returns:
    - str: The generated filename if successful, otherwise the original filename without extension.
    """
    logger.info(f"Generating filename for {item.local_file_path}")

    # Get PDF Text
    pdf_text = extract_text(item.ocr_file)

    if not pdf_text:
        logger.warning("Failed to extract text from PDF. Using default filename.")
        return item.filename_without_extension

    client = OpenAI(
        api_key=openai_settings.api_key,
    )

    try:
        # Retry logic for OpenAI API calls
        retry_strategy = Retrying(
            stop=stop_after_attempt(6),
            wait=wait_random_exponential(multiplier=10, min=10, max=120),
            retry=retry_if_exception_type(RateLimitError),
            after=lambda retry_state: logger.warning(
                f"Attempt nr {retry_state.attempt_number} failed with exception: {retry_state.outcome.exception()}, waited {round(retry_state.upcoming_sleep, 1)} seconds"
            ),
        )
        for attempt in retry_strategy:
            with attempt:
                openai_filename = client.responses.create(
                    model=OPENAI_MODEL,
                    instructions="Identify a suitable filename for the following pdf content. Keep the language of the file name in the original language and do not add any other language. Make the filename safe for SMB. Do not add a file extension. Seperate words with a underscore. Have a maximum filename length of 50 characters.",
                    input=pdf_text,
                )
        if openai_filename:
            logger.debug(f"Received OpenAI filename: {openai_filename.output_text}")
            sanitized_filename = validate_smb_filename(openai_filename.output_text)
            logger.debug(f"Sanitized OpenAI filename: {sanitized_filename}")
            return sanitized_filename
        else:
            logger.warning("OpenAI key worked, but did not return any result.")
            return item.filename_without_extension
    except AuthenticationError:
        logger.warning("OpenAI key is invalid or wrong permissions set.")
        return item.filename_without_extension
    except RetryError as retryerr:
        logger.warning(f"OpenAI rate limit reached! Either not enough credits or too many requests. Tried {retryerr.last_attempt.attempt_number} times.")
        return item.filename_without_extension
    except Exception:
        logger.exception("An error occurred while creating a file name.")
        return item.filename_without_extension
    finally:
        # Close the OpenAI client connection
        client.close()


def validate_smb_filename(filename: str) -> str:
    """
    Validates and adjusts a string to be a valid Windows SMB filename (without extension)
    and ensures it is at most 50 characters long.

    Parameters:
    - filename (str): The input filename to validate.

    Returns:
    - str: A valid SMB filename.
    """
    # Remove invalid characters for Windows filenames
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
    filename = re.sub(invalid_chars, '', filename)

    # Trim whitespace and dots before length cutoff
    filename = filename.strip().strip('.')

    # Ensure the filename is at most 50 characters
    if len(filename) > 50:
        filename = filename[:50]

    # Final trim in case length cutoff introduced trailing space or dot
    filename = filename.strip().strip('.')

    # Ensure filename is not empty after sanitization
    if not filename:
        filename = "default_filename"

    return filename


def extract_text(pdf_path: str) -> str:
    """Extracts text from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        str: The extracted text from the PDF. An empty string is returned if the extraction fails.
    """
    try:
        reader = PdfReader(pdf_path)
        page = reader.pages[0]
        text = page.extract_text()
        return text
    except Exception as ex:
        logger.exception(f"Failed extracting text: {ex}")
        return ""
