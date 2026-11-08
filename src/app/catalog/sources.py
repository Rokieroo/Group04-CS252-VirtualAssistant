"""The catalog source registry, ``data/policy/catalog_sources.yaml`` (ADR 004).

Connectors and the ingest step read providers and licenses from here, never from
a copy, so adding or restricting a provider stays a reviewed data change.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.catalog.institutions import matches_domain

PATH = Path(__file__).resolve().parents[3] / "data/policy/catalog_sources.yaml"


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    use: str  # source | authority
    levels: tuple[str, ...]
    domains: tuple[str, ...]
    licenses: tuple[str, ...]  # the one license, or the item licenses of `per_item`
    method: str  # api | sitemap | manual
    endpoint: str | None
    automated: bool
    rate_limit_per_sec: float | None

    def owns(self, url: str) -> bool:
        return any(matches_domain(url, domain) for domain in self.domains)


@dataclass(frozen=True)
class Sources:
    licenses: dict[str, dict]
    providers: dict[str, Provider]

    def provider_of(self, url: str) -> Provider | None:
        return next((p for p in self.providers.values() if p.owns(url)), None)

    def rate_limits(self) -> dict[str, float]:
        """Requests per second allowed on each domain an automated provider owns."""
        return {
            domain: p.rate_limit_per_sec
            for p in self.providers.values()
            if p.automated and p.rate_limit_per_sec
            for domain in p.domains
        }


def _provider(row: dict) -> Provider:
    per_item = row["license"] == "per_item"
    return Provider(
        id=row["id"],
        name=row["name"],
        use=row["use"],
        levels=tuple(row["levels"]),
        domains=tuple(row["domains"]),
        licenses=tuple(row["item_licenses"] if per_item else [row["license"]]),
        method=row["method"],
        endpoint=row["endpoint"],
        automated=bool(row["automated"]),
        rate_limit_per_sec=row["rate_limit_per_sec"],
    )


@lru_cache(maxsize=1)
def load_sources(path: Path = PATH) -> Sources:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Sources(
        licenses=data["licenses"],
        providers={row["id"]: _provider(row) for row in data["providers"]},
    )
