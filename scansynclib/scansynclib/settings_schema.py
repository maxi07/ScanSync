from enum import Enum
from typing import Annotated
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

    ollama_server_port: Annotated[int, Field(strict=True, ge=1, le=65535, description="Ollama server port for file naming")] = 11434

    ollama_model: str = Field("", description="Ollama model for file naming")
    """Ollama model for file naming, e.g., 'llama2'."""


class OneDriveSettings(BaseModel):
    """Settings for OneDrive integration."""

    client_id: str = Field("", description="OneDrive client ID")
    """OneDrive client ID for authentication."""

    authority: str = Field("https://login.microsoftonline.com/consumers", description="OneDrive authority URL")
    """OneDrive authority URL for authentication."""

    scope: list[str] = Field(default_factory=lambda: ['Files.ReadWrite', 'User.Read'], description="OneDrive scope for permissions")
    """OneDrive scope for permissions, defaulting to read/write access."""


class SettingsSchema(BaseModel):
    file_naming: FileNamingSettings = FileNamingSettings()
    """Settings for file naming, including OpenAI and Ollama configurations."""

    onedrive: OneDriveSettings = OneDriveSettings()
    """Settings for OneDrive integration, including client ID and authority URL."""
