from enum import Enum
from pydantic import BaseModel, Field


class FileNamingMethod(Enum):
    """Enum for file naming methods."""
    OPENAI = "openai"
    OLLAMA = "ollama"
    NONE = "none"


class FileNamingSettings(BaseModel):
    """Settings for file naming using OpenAI or Ollama."""

    method: FileNamingMethod = Field(FileNamingMethod.NONE)
    """The method to use for file naming."""

    openai_api_key: str = Field("", description="OpenAI API key for file naming")
    """OpenAI API key for file naming."""

    ollama_server_url: str = Field("", description="Ollama server URL for file naming")
    """Ollama server URL for file naming, eg 'localhost'."""

    ollama_server_port: int = Field(11434, description="Ollama server port for file naming")
    """Ollama server port for file naming, default is 11434."""

    ollama_model: str = Field("", description="Ollama model for file naming")
    """Ollama model for file naming, e.g., 'llama2'."""


class SettingsSchema(BaseModel):
    file_naming: FileNamingSettings = FileNamingSettings()
    """Settings for file naming, including OpenAI and Ollama configurations."""
