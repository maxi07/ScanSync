from requests import request
from scansynclib.ProcessItem import ProcessItem
from scansynclib.helpers import extract_text
from scansynclib.logging import logger
import html


def generate_ollama_filename(server_url: str, model: str, item: ProcessItem) -> str:
    """
    Generate a filename using the Ollama model.

    Args:
        server_url (str): The URL of the Ollama server.
        model (str): The name of the Ollama model to use.
        item (ProcessItem): The ProcessItem containing details for filename generation.

    Returns:
        str: The generated filename.
    """
    pdftext = extract_text(item.ocr_file)
    if not pdftext:
        logger.warning("Failed to extract text from PDF. Using default filename.")
        return item.filename_without_extension

    return send_request_to_ollama(server_url, model, pdftext)


def send_request_to_ollama(server_url: str, model: str, pdftext: str) -> str:
    """
    Send a request to the Ollama server to generate a filename.

    Args:
        server_url (str): The URL of the Ollama server.
        model (str): The name of the Ollama model to use.
        pdftext (str): The text extracted from the PDF.

    Returns:
        str: The generated filename.
    """
    systemprompt = "Identify a suitable filename for the following pdf content. Keep the language of the file name in the original language and do not add any other language. Make the filename safe for SMB. Do not add a file extension. Seperate words with a underscore. Have a maximum filename length of 50 characters. Only respond with the filename."

    try:
        res = request.post(
            f"{server_url}/api/generate",
            json={
                "model": model,
                "prompt": html.escape(pdftext),
                "stream": False,
                "system": html.escape(systemprompt),
            },
        )
        res.raise_for_status()
        response_data = res.json()
        return response_data.get("response", "")
    except Exception as e:
        logger.exception(f"Failed to send request to Ollama: {e}")
        return ""


def get_ollama_version(server_url: str) -> str:
    """
    Get the version of the Ollama server.

    Args:
        server_url (str): The URL of the Ollama server.

    Returns:
        str: The version of the Ollama server.
    """
    try:
        res = request.get(f"{server_url}/api/version")
        res.raise_for_status()
        return res.json().get("version", "Unknown version")
    except Exception as e:
        logger.exception(f"Failed to get Ollama version: {e}")
        return "Unknown version"
