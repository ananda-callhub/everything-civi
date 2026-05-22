from __future__ import annotations

import httpx
from typing import Any

from everything_civi.config import CiviCRMConfig


class CiviCRMAPIError(Exception):
    """Raised when CiviCRM returns an application-level error."""

    def __init__(self, error_message: str, error_code: int = 0) -> None:
        self.error_code = error_code
        self.error_message = error_message
        super().__init__(f"CiviCRM API error ({error_code}): {error_message}")


class CiviCRMClient:
    """Async HTTP client for the CiviCRM APIv4 REST interface."""

    def __init__(self, config: CiviCRMConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                verify=self._config.verify_ssl,
                timeout=httpx.Timeout(self._config.timeout),
            )
        return self._client

    async def api4(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self._get_client()
        url = f"/civicrm/ajax/api4/{entity}/{action}"
        body = params if params is not None else {}

        try:
            response = await client.post(url, json=body)
            response.raise_for_status()
        except httpx.TimeoutException:
            raise CiviCRMAPIError(error_message=f"Request timed out: {url}")
        except httpx.HTTPStatusError as exc:
            raise CiviCRMAPIError(
                error_message=f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:500]}",
                error_code=exc.response.status_code,
            )
        except httpx.HTTPError as exc:
            raise CiviCRMAPIError(error_message=f"HTTP error: {exc}")

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type and "text/json" not in content_type:
            raise CiviCRMAPIError(
                error_message=(
                    "Expected JSON response but received "
                    f"{content_type!r}. This usually indicates an "
                    "authentication failure or misconfigured URL."
                ),
            )

        data = response.json()

        if "error_message" in data:
            raise CiviCRMAPIError(
                error_message=data["error_message"],
                error_code=data.get("error_code", 0),
            )

        return data

    # -- Convenience methods ---------------------------------------------------

    async def get(self, entity: str, **params: Any) -> dict[str, Any]:
        return await self.api4(entity, "get", params or None)

    async def create(self, entity: str, values: dict[str, Any]) -> dict[str, Any]:
        return await self.api4(entity, "create", {"values": values})

    async def update(
        self,
        entity: str,
        values: dict[str, Any],
        where: list[Any],
    ) -> dict[str, Any]:
        return await self.api4(entity, "update", {"values": values, "where": where})

    async def delete(
        self,
        entity: str,
        where: list[Any],
        use_trash: bool = True,
    ) -> dict[str, Any]:
        return await self.api4(entity, "delete", {"where": where, "useTrash": use_trash})

    async def save(
        self,
        entity: str,
        records: list[dict[str, Any]],
        match: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"records": records}
        if match is not None:
            params["match"] = match
        return await self.api4(entity, "save", params)

    async def replace(
        self,
        entity: str,
        records: list[dict[str, Any]],
        where: list[Any],
    ) -> dict[str, Any]:
        return await self.api4(entity, "replace", {"records": records, "where": where})

    async def get_fields(
        self,
        entity: str,
        action: str = "get",
        load_options: bool | list[str] = False,
    ) -> dict[str, Any]:
        return await self.api4(
            entity,
            "getFields",
            {"action": action, "loadOptions": load_options},
        )

    async def get_actions(self, entity: str) -> dict[str, Any]:
        return await self.api4(entity, "getActions")

    # -- Lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "CiviCRMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
