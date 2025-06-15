from scansynclib.ProcessItem import ProcessItem
from scansynclib.helpers import extract_text


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

    raise NotImplementedError("Ollama filename generation is not implemented yet.")
