"""Catalog connectors (#98): one per provider of ``catalog_sources.yaml``, plus the
hand-added sources. :func:`build_connectors` is the only place that wires them.
"""

from collections.abc import Callable, Iterable
from pathlib import Path

from app.catalog.connectors.base import (
    CatalogConnector,
    CatalogRecord,
    ConnectorError,
    FakeConnector,
    Fetcher,
    UnitRecord,
    check_record,
    labels,
    wanted,
)
from app.catalog.connectors.manual_yaml import ManualYamlConnector
from app.catalog.connectors.mit_ocw import MitOcwConnector
from app.catalog.connectors.openstax import OpenStaxConnector
from app.catalog.sources import Provider, Sources, load_sources

__all__ = [
    "CONNECTORS",
    "CatalogConnector",
    "CatalogRecord",
    "ConnectorError",
    "FakeConnector",
    "ManualYamlConnector",
    "MitOcwConnector",
    "OpenStaxConnector",
    "UnitRecord",
    "build_connectors",
    "check_record",
    "labels",
    "wanted",
]

DATA = Path(__file__).resolve().parents[4] / "data/catalog"
# The internal catalog (spec 11.2) still serves computer_science.yaml as it is;
# files under sources/ reach learners only after verification.
MANUAL_FILES = [DATA / "computer_science.yaml", DATA / "sources/manual.yaml"]
OPEN_YALE_FILE = DATA / "sources/open_yale.yaml"


def _automated(provider: Provider, method: str) -> Provider:
    """ADR 004 section 9: no program touches a provider whose terms forbid it."""
    if not provider.automated or provider.method != method or not provider.endpoint:
        raise ConnectorError(f"not_automatable_{provider.id}")
    return provider


Factory = Callable[[Fetcher, Sources], CatalogConnector]

CONNECTORS: dict[str, Factory] = {
    "mit_ocw": lambda fetcher, sources: MitOcwConnector(
        _automated(sources.providers["mit_ocw"], "sitemap"), fetcher
    ),
    "openstax": lambda fetcher, sources: OpenStaxConnector(
        _automated(sources.providers["openstax"], "api"), fetcher
    ),
    "open_yale": lambda fetcher, sources: ManualYamlConnector(
        [OPEN_YALE_FILE], sources, name="open_yale"
    ),
    "manual_yaml": lambda fetcher, sources: ManualYamlConnector(MANUAL_FILES, sources),
}


def build_connectors(
    fetcher: Fetcher,
    names: Iterable[str] | None = None,
    sources: Sources | None = None,
) -> list[CatalogConnector]:
    """The named connectors (default: all), in the order given."""
    sources = sources or load_sources()
    chosen = list(names or CONNECTORS)
    unknown = [name for name in chosen if name not in CONNECTORS]
    if unknown:
        raise ConnectorError("unknown_connector_" + unknown[0])
    return [CONNECTORS[name](fetcher, sources) for name in chosen]
