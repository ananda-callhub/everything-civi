from pydantic_settings import BaseSettings


class CiviCRMConfig(BaseSettings):
    """Configuration for connecting to a CiviCRM instance."""

    base_url: str
    api_key: str
    site_key: str = ""
    verify_ssl: bool = True
    timeout: int = 30

    model_config = {
        "env_prefix": "CIVICRM_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }
