import requests
from scansynclib.logging import logger


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
