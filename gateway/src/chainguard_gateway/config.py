"""Validated process settings; no credentials or business configuration are loaded."""
import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    app_env: Literal["local", "test", "container"] = "local"
    host: Literal["127.0.0.1", "0.0.0.0", "::1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: Literal["critical", "error", "warning", "info", "debug"] = "info"
    shutdown_timeout: int = Field(default=5, ge=1, le=30)


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if environ is None else environ
    fields = {
        "CHG_APP_ENV": "app_env", "CHG_HOST": "host", "CHG_PORT": "port",
        "CHG_LOG_LEVEL": "log_level", "CHG_SHUTDOWN_TIMEOUT": "shutdown_timeout",
    }
    return Settings.model_validate({field: source[key] for key, field in fields.items() if key in source})
