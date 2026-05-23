from __future__ import annotations

import copy
import os
from typing import Any
import pytest

from everything_civi.client import CiviCRMAPIError, CiviCRMClient
from everything_civi.config import CiviCRMConfig


class MockCiviCRMClient:
    """Test double for CiviCRMClient that records calls and returns canned responses."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None, str | None]] = []
        self._responses: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, CiviCRMAPIError] = {}
        self._sequences: dict[str, list[dict[str, Any]]] = {}
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

    def set_response_sequence(
        self,
        entity: str,
        action: str,
        responses: list[dict[str, Any]],
    ) -> None:
        """Set a sequence of responses returned in order. After exhaustion, returns the last one."""
        self._sequences[f"{entity}.{action}"] = list(responses)

    async def api4(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((entity, action, copy.deepcopy(params), token))
        key = f"{entity}.{action}"
        if key in self._errors:
            raise self._errors[key]
        if key in self._sequences:
            seq = self._sequences[key]
            if len(seq) > 1:
                return seq.pop(0)
            return seq[0]  # repeat last response
        if key in self._responses:
            return self._responses[key]
        return dict(self._default_response)

    async def get(
        self, entity: str, *, token: str | None = None, **params: Any,
    ) -> dict[str, Any]:
        return await self.api4(entity, "get", params or None, token=token)

    async def create(
        self, entity: str, values: dict[str, Any], *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "create", {"values": values}, token=token)

    async def get_fields(
        self,
        entity: str,
        action: str = "get",
        load_options: bool | list[str] = False,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(
            entity, "getFields",
            {"action": action, "loadOptions": load_options},
            token=token,
        )

    async def update(
        self, entity: str, values: dict[str, Any], where: list[Any],
        *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "update", {"values": values, "where": where}, token=token)

    async def delete(
        self, entity: str, where: list[Any], use_trash: bool = True,
        *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "delete", {"where": where, "useTrash": use_trash}, token=token)

    async def save(
        self, entity: str, records: list[dict[str, Any]], match: list[str] | None = None,
        *, token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"records": records}
        if match is not None:
            params["match"] = match
        return await self.api4(entity, "save", params, token=token)

    async def replace(
        self, entity: str, records: list[dict[str, Any]], where: list[Any],
        *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "replace", {"records": records, "where": where}, token=token)

    async def get_actions(
        self, entity: str, *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "getActions", token=token)

    async def health_check(self) -> dict[str, Any]:
        """Check connectivity and return server info (mirrors CiviCRMClient)."""
        try:
            result = await self.api4("System", "check", {})
            return {"status": "ok", "checks": result.get("values", [])}
        except CiviCRMAPIError as exc:
            return {"status": "error", "error": str(exc)}

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
