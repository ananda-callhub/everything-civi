from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
from typing import Any

from everything_civi.config import CiviCRMConfig

logger = logging.getLogger("everything_civi.audit")

# Entities whose param keys should never be logged (PII / security risk).
_SENSITIVE_ENTITIES = frozenset({
    "Contact", "Email", "Phone", "Address", "Individual", "Household",
    "Organization", "Note", "Relationship", "IM", "Website", "OpenID",
    "Contribution", "Pledge", "Participant", "Case", "GroupContact",
})


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
        self._semaphore: asyncio.Semaphore | None = None
        self._max_concurrent = config.max_concurrent
        self._max_retries = config.max_retries
        self._retry_delay = config.retry_delay

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "X-Requested-With": "XMLHttpRequest",
                },
                verify=self._config.verify_ssl,
                timeout=httpx.Timeout(self._config.timeout),
            )
        return self._client

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    def _audit_param_keys(
        self, entity: str, params: dict[str, Any] | None,
    ) -> list[str] | None:
        """Return top-level param keys for logging, or None for sensitive entities."""
        if entity in _SENSITIVE_ENTITIES:
            return None
        return list(params.keys()) if params else []

    @staticmethod
    def _audit_error_msg(entity: str, error: Exception) -> str:
        if entity in _SENSITIVE_ENTITIES:
            return f"[redacted — {type(error).__name__}]"
        return str(error)

    async def api4(
        self,
        entity: str,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        audit = self._config.audit_log
        start_time = time.monotonic()
        param_keys = self._audit_param_keys(entity, params) if audit else None

        client = self._get_client()
        semaphore = self._get_semaphore()
        url = f"/civicrm/ajax/api4/{entity}/{action}"
        form_data = {"params": json.dumps(params)} if params else {}

        last_error: CiviCRMAPIError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                request_headers = (
                    {"Authorization": f"Bearer {token}"} if token else None
                )
                async with semaphore:
                    response = await client.post(
                        url, data=form_data, headers=request_headers,
                    )
                    response.raise_for_status()
            except httpx.TimeoutException:
                last_error = CiviCRMAPIError(
                    error_message=f"Request timed out: {url}",
                )
                if attempt < self._max_retries:
                    if audit:
                        logger.info(
                            "api4_retry",
                            extra={
                                "entity": entity,
                                "action": action,
                                "attempt": attempt + 1,
                                "retry_reason": "timeout",
                            },
                        )
                    await asyncio.sleep(self._retry_delay * (2**attempt))
                    continue
                if audit:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    logger.warning(
                        "api4_call",
                        extra={
                            "entity": entity,
                            "action": action,
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error_type": "TimeoutException",
                            "error_message": self._audit_error_msg(entity, last_error),
                            "param_keys": param_keys,
                        },
                    )
                raise last_error
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    last_error = CiviCRMAPIError(
                        error_message=(
                            f"HTTP {exc.response.status_code} from "
                            f"{url}: {exc.response.text[:500]}"
                        ),
                        error_code=exc.response.status_code,
                    )
                    if attempt < self._max_retries:
                        if audit:
                            logger.info(
                                "api4_retry",
                                extra={
                                    "entity": entity,
                                    "action": action,
                                    "attempt": attempt + 1,
                                    "retry_reason": f"http_{exc.response.status_code}",
                                },
                            )
                        await asyncio.sleep(self._retry_delay * (2**attempt))
                        continue
                    if audit:
                        duration_ms = (time.monotonic() - start_time) * 1000
                        logger.warning(
                            "api4_call",
                            extra={
                                "entity": entity,
                                "action": action,
                                "duration_ms": round(duration_ms, 2),
                                "status": "error",
                                "error_type": "HTTPStatusError",
                                "error_message": self._audit_error_msg(entity, last_error),
                                "param_keys": param_keys,
                            },
                        )
                    raise last_error
                non_retryable = CiviCRMAPIError(
                    error_message=(
                        f"HTTP {exc.response.status_code} from "
                        f"{url}: {exc.response.text[:500]}"
                    ),
                    error_code=exc.response.status_code,
                )
                if audit:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    logger.warning(
                        "api4_call",
                        extra={
                            "entity": entity,
                            "action": action,
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error_type": "HTTPStatusError",
                            "error_message": self._audit_error_msg(entity, non_retryable),
                            "param_keys": param_keys,
                        },
                    )
                raise non_retryable
            except httpx.HTTPError as exc:
                last_error = CiviCRMAPIError(
                    error_message=f"HTTP error: {exc}",
                )
                if attempt < self._max_retries:
                    if audit:
                        logger.info(
                            "api4_retry",
                            extra={
                                "entity": entity,
                                "action": action,
                                "attempt": attempt + 1,
                                "retry_reason": "http_error",
                            },
                        )
                    await asyncio.sleep(self._retry_delay * (2**attempt))
                    continue
                if audit:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    logger.warning(
                        "api4_call",
                        extra={
                            "entity": entity,
                            "action": action,
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error_type": "HTTPError",
                            "error_message": self._audit_error_msg(entity, last_error),
                            "param_keys": param_keys,
                        },
                    )
                raise last_error

            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                api_err = CiviCRMAPIError(
                    error_message=(
                        "Expected JSON response but received "
                        f"{content_type!r}. This usually indicates an "
                        "authentication failure or misconfigured URL."
                    ),
                )
                if audit:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    logger.warning(
                        "api4_call",
                        extra={
                            "entity": entity,
                            "action": action,
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error_type": "CiviCRMAPIError",
                            "error_message": self._audit_error_msg(entity, api_err),
                            "param_keys": param_keys,
                        },
                    )
                raise api_err

            data = response.json()

            if "error_message" in data:
                api_err = CiviCRMAPIError(
                    error_message=data["error_message"],
                    error_code=data.get("error_code", 0),
                )
                if audit:
                    duration_ms = (time.monotonic() - start_time) * 1000
                    logger.warning(
                        "api4_call",
                        extra={
                            "entity": entity,
                            "action": action,
                            "duration_ms": round(duration_ms, 2),
                            "status": "error",
                            "error_type": "CiviCRMAPIError",
                            "error_message": self._audit_error_msg(entity, api_err),
                            "param_keys": param_keys,
                        },
                    )
                raise api_err

            if audit:
                duration_ms = (time.monotonic() - start_time) * 1000
                logger.info(
                    "api4_call",
                    extra={
                        "entity": entity,
                        "action": action,
                        "duration_ms": round(duration_ms, 2),
                        "status": "success",
                        "param_keys": param_keys,
                    },
                )
            return data

        raise last_error  # type: ignore[misc]

    async def health_check(self) -> dict[str, Any]:
        """Check connectivity and return server info."""
        try:
            result = await self.api4("System", "check", {})
            return {"status": "ok", "checks": result.get("values", [])}
        except CiviCRMAPIError as exc:
            return {"status": "error", "error": str(exc)}

    # -- Convenience methods ---------------------------------------------------

    async def get(
        self, entity: str, *, token: str | None = None, **params: Any,
    ) -> dict[str, Any]:
        return await self.api4(entity, "get", params or None, token=token)

    async def create(
        self, entity: str, values: dict[str, Any], *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "create", {"values": values}, token=token)

    async def update(
        self,
        entity: str,
        values: dict[str, Any],
        where: list[Any],
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(
            entity, "update", {"values": values, "where": where}, token=token,
        )

    async def delete(
        self,
        entity: str,
        where: list[Any],
        use_trash: bool = True,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(
            entity, "delete", {"where": where, "useTrash": use_trash}, token=token,
        )

    async def save(
        self,
        entity: str,
        records: list[dict[str, Any]],
        match: list[str] | None = None,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"records": records}
        if match is not None:
            params["match"] = match
        return await self.api4(entity, "save", params, token=token)

    async def replace(
        self,
        entity: str,
        records: list[dict[str, Any]],
        where: list[Any],
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(
            entity, "replace", {"records": records, "where": where}, token=token,
        )

    async def get_fields(
        self,
        entity: str,
        action: str = "get",
        load_options: bool | list[str] = False,
        *,
        token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(
            entity,
            "getFields",
            {"action": action, "loadOptions": load_options},
            token=token,
        )

    async def get_actions(
        self, entity: str, *, token: str | None = None,
    ) -> dict[str, Any]:
        return await self.api4(entity, "getActions", token=token)

    # -- Lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._semaphore = None

    async def __aenter__(self) -> "CiviCRMClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
