"""HTTP client for RadMachine."""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterator
from typing import TypeVar
from urllib.parse import urljoin

import requests

from .config import Config, get_token, validate_radmachine_config
from .rm_models import (
    ApiObject,
    ServiceEvent,
    ServiceLogReturnToServiceQA,
    TestInstance,
    TestListInstance,
    Unit,
    UnitTestCollection,
)

ApiModel = TypeVar("ApiModel", bound=ApiObject)


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

    def qa_test_list_instances(self, params: dict[str, str] | None = None) -> Iterator[TestListInstance]:
        """Return performed QA sessions from `qa/testlistinstances`."""
        return self._typed_paginate("qa/testlistinstances", TestListInstance.from_api, params=params)

    def qa_test_instances(self, params: dict[str, str] | None = None) -> Iterator[TestInstance]:
        """Return individual QA result rows from `qa/testinstances`."""
        return self._typed_paginate("qa/testinstances", TestInstance.from_api, params=params)

    def qa_unit_test_collections(self, params: dict[str, str] | None = None) -> Iterator[UnitTestCollection]:
        """Return unit/test-list assignments from `qa/unittestcollections`."""
        return self._typed_paginate("qa/unittestcollections", UnitTestCollection.from_api, params=params)

    def units(self, params: dict[str, str] | None = None) -> Iterator[Unit]:
        """Return treatment/unit records from `units/units`."""
        return self._typed_paginate("units/units", Unit.from_api, params=params)

    def service_events(self, params: dict[str, str] | None = None) -> Iterator[ServiceEvent]:
        """Return service event records from `servicelog/serviceevents`."""
        return self._typed_paginate("servicelog/serviceevents", ServiceEvent.from_api, params=params)

    def service_log_return_to_service_qa(
        self, params: dict[str, str] | None = None
    ) -> Iterator[ServiceLogReturnToServiceQA]:
        """Return service-log RTS QA links from `servicelog/returntoserviceqa`."""
        return self._typed_paginate(
            "servicelog/returntoserviceqa",
            ServiceLogReturnToServiceQA.from_api,
            params=params,
        )

    def qa_unit_test_collection(self, endpoint: str) -> UnitTestCollection:
        """Fetch one unit/test-list assignment by API URL or endpoint."""
        return UnitTestCollection.from_api(self._get_object(endpoint))

    def unit(self, endpoint: str) -> Unit:
        """Fetch one unit by API URL or endpoint."""
        return Unit.from_api(self._get_object(endpoint))

    def _typed_paginate(
        self,
        endpoint: str,
        factory: Callable[[dict], ApiModel],
        params: dict[str, str] | None = None,
    ) -> Iterator[ApiModel]:
        for payload in self.paginate(endpoint, params=params):
            if not isinstance(payload, dict):
                raise ValueError(f"Expected object payload from {endpoint}")
            yield factory(payload)

    def _get_object(self, endpoint: str) -> dict:
        payload = self.get_json(endpoint)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object payload from {endpoint}")
        return payload

    def _build_url(self, endpoint: str) -> str:
        if not endpoint:
            return self.api_root_url

        cleaned = endpoint.lstrip("/")
        if cleaned.startswith(f"{self._config.radmachine.customer_id}/api/"):
            return urljoin(self._config.radmachine.base_url.rstrip("/") + "/", cleaned)
        return urljoin(self.api_root_url, cleaned)
