from enum import Enum
from pydantic import BaseModel, Field


class FileNamingMethod(Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    NONE = "none"


class FileNamingSettings(BaseModel):
    method: FileNamingMethod = Field(FileNamingMethod.NONE)
    """The method to use for file naming."""
    model: str = Field("")
    """The model to use for file naming, e.g., 'gpt-4' or 'ollama/llama2'."""


class OCRSettings(BaseModel):
    language: str = Field("de", description="Erkennungssprache")


class SettingsSchema(BaseModel):
    file_naming: FileNamingSettings = FileNamingSettings()
    ocr: OCRSettings = OCRSettings()
