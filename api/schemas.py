from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    gemini_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class GenerateRequest(BaseModel):
    job_title: str = Field(min_length=2, max_length=120)

    @field_validator("job_title")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("job_title must contain at least 2 non-whitespace characters.")
        return stripped


class GenerateResponse(BaseModel):
    job_title: str
    questions: list[str]


class ErrorResponse(BaseModel):
    code: str
    message: str
