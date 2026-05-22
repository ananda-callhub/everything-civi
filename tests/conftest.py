from __future__ import annotations

import os
from typing import Any
import pytest

from everything_civi.client import CiviCRMAPIError, CiviCRMClient
from everything_civi.config import CiviCRMConfig


class MockCiviCRMClient:
    """Test double for CiviCRMClient that records calls and returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []
        self._responses: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, CiviCRMAPIError] = {}
        self._default_response: dict[str, Any] = {"values": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def set_response(
        self,
        entity: str,
        action: str,
        response: dict[str, Any],
    ) -> None:
        self._responses[f"{entity}.{action}"] = response

    def set_error(
        self,
        entity: str,
        action: str,
        error_message: str,
        error_code: int = 0,
    ) -> None:
        self._errors[f"{entity}.{action}"] = CiviCRMAPIError(error_message, error_code)

    async def api4(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((entity, action, params))
        key = f"{entity}.{action}"
        if key in self._errors:
            raise self._errors[key]
        if key in self._responses:
            return self._responses[key]
        return dict(self._default_response)

    async def get(self, entity: str, **params: Any) -> dict[str, Any]:
        return await self.api4(entity, "get", params or None)

    async def create(self, entity: str, values: dict[str, Any]) -> dict[str, Any]:
        return await self.api4(entity, "create", {"values": values})

    async def get_fields(
        self,
        entity: str,
        action: str = "get",
        load_options: bool | list[str] = False,
    ) -> dict[str, Any]:
        return await self.api4(
            entity, "getFields",
            {"action": action, "loadOptions": load_options},
        )

    async def get_actions(self, entity: str) -> dict[str, Any]:
        return await self.api4(entity, "getActions")

    async def close(self) -> None:
        pass


@pytest.fixture
def mock_client() -> MockCiviCRMClient:
    return MockCiviCRMClient()


@pytest.fixture
def live_client() -> CiviCRMClient | None:
    """Create a real CiviCRMClient if env vars are set. Returns None otherwise."""
    base_url = os.environ.get("CIVICRM_BASE_URL")
    api_key = os.environ.get("CIVICRM_API_KEY")
    if not base_url or not api_key:
        return None
    config = CiviCRMConfig()
    return CiviCRMClient(config)


def requires_live_instance(fn):
    """Decorator that skips a test if live CiviCRM credentials are not configured."""
    return pytest.mark.skipif(
        not os.environ.get("CIVICRM_BASE_URL") or not os.environ.get("CIVICRM_API_KEY"),
        reason="CIVICRM_BASE_URL and CIVICRM_API_KEY required for integration tests",
    )(fn)
