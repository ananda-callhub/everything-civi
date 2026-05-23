from pydantic import Field
from pydantic_settings import BaseSettings


class CiviCRMConfig(BaseSettings):
    """Configuration for connecting to a CiviCRM instance."""

    base_url: str
    api_key: str
    site_key: str = ""
    verify_ssl: bool = True
    timeout: int = Field(default=30, ge=1)
    max_retries: int = Field(default=2, ge=0)
    retry_delay: float = Field(default=1.0, ge=0)
    max_concurrent: int = Field(default=5, ge=1)

    model_config = {
        "env_prefix": "CIVICRM_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
