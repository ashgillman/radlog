from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def local_radmachine_config() -> tuple[str, str]:
    config_path = Path(__file__).resolve().parents[1] / "config.toml"
    if config_path.exists():
        with config_path.open("rb") as handle:
            payload = tomllib.load(handle)
        radmachine = payload.get("radmachine", {})
        base_url = str(radmachine.get("base_url", "")).strip()
        customer_id = str(radmachine.get("customer_id", "")).strip()
        if base_url and customer_id:
            return base_url, customer_id
    return "https://example.invalid", "example"


TEST_BASE_URL, TEST_CUSTOMER_ID = local_radmachine_config()
