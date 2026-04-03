"""HTTP client for RadMachine."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urljoin

import requests

from .config import Config, get_token, validate_radmachine_config


class RadMachineClient:
    """Small authenticated client for the RadMachine API."""

    def __init__(self, config: Config, session: requests.Session | None = None) -> None:
        validate_radmachine_config(config)
        token = get_token(config)

        self._config = config
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "RadAuthorization": f"Token {token}",
            }
        )

    @property
    def api_root_url(self) -> str:
        base_url = self._config.radmachine.base_url.rstrip("/")
        customer_id = self._config.radmachine.customer_id.strip("/")
        return f"{base_url}/{customer_id}/api/"

    def get_json(self, endpoint: str = "", params: dict[str, str] | None = None) -> dict | list:
        url = self._build_url(endpoint)
        response = self._session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def paginate(self, endpoint: str, params: dict[str, str] | None = None) -> Iterator[dict]:
        next_url: str | None = self._build_url(endpoint)
        next_params = params

        while next_url:
            response = self._session.get(next_url, params=next_params, timeout=30)
            response.raise_for_status()
            payload = response.json()

            if not isinstance(payload, dict) or "results" not in payload:
                raise ValueError("Expected a DRF-style paginated response with a results key")

            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ValueError("Expected results to be a list")

            yield from results
            next_url = payload.get("next")
            next_params = None

    def _build_url(self, endpoint: str) -> str:
        if not endpoint:
            return self.api_root_url

        cleaned = endpoint.lstrip("/")
        if cleaned.startswith(f"{self._config.radmachine.customer_id}/api/"):
            return urljoin(self._config.radmachine.base_url.rstrip("/") + "/", cleaned)
        return urljoin(self.api_root_url, cleaned)
