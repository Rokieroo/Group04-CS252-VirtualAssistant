"""Domain policy: blocklist, authority tiers, and known paywalls (spec 11.3-11.4).

The lists live in ``data/policy/*.txt`` so the team edits policy without
touching code; the institution registry (#96, ``data/catalog/institutions.csv``)
adds the domains of ranked institutions at their tier.  Matching walks the
host's labels against hash sets, so a check costs the same no matter how long
the lists grow.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import IntEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

__all__ = ["DEFAULT_POLICY_DIR", "DomainPolicy", "DomainTier", "default_policy", "domain_tier"]

DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[3] / "data" / "policy"
DEFAULT_REGISTRY = Path(__file__).resolve().parents[3] / "data" / "catalog" / "institutions.csv"


class DomainTier(IntEnum):
    """Lower is more trusted; ``BLOCKED`` is never shown."""

    BLOCKED = 0
    TIER1 = 1
    TIER2 = 2
    OTHER = 3


@dataclass(frozen=True)
class _Rules:
    """Entries from one list: exact suffixes, and ``name.*`` bases."""

    suffixes: frozenset[str]
    any_tld: frozenset[str]

    @classmethod
    def read(cls, path: Path) -> _Rules:
        suffixes, any_tld = set(), set()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = line.split("#", 1)[0].strip().casefold().strip(".")
                entry = entry.removeprefix("*.")
                if not entry:
                    continue
                if entry.endswith(".*"):
                    any_tld.add(entry[:-2])
                else:
                    suffixes.add(entry)
        return cls(frozenset(suffixes), frozenset(any_tld))

    def union(self, domains: frozenset[str]) -> _Rules:
        return _Rules(self.suffixes | domains, self.any_tld)

    def match(self, labels: list[str]) -> bool:
        # Suffix entry: the host is the entry or one of its subdomains.
        if any(".".join(labels[i:]) in self.suffixes for i in range(len(labels))):
            return True
        # "name.*" entry: the name followed by at least one more label.
        return any(
            ".".join(labels[i:j]) in self.any_tld
            for i in range(len(labels))
            for j in range(i + 1, len(labels))
        )


def _labels(url: str) -> list[str]:
    try:
        host = urlsplit(url.strip()).hostname or ""
    except ValueError:
        return []
    return [label for label in host.casefold().strip(".").split(".") if label]


@dataclass(frozen=True)
class DomainPolicy:
    blocked: _Rules
    tier1: _Rules
    tier2: _Rules
    paywalled: _Rules

    @classmethod
    def load(
        cls, directory: str | Path = DEFAULT_POLICY_DIR, registry: str | Path | None = None
    ) -> DomainPolicy:
        """Read the four lists, plus the institution ``registry`` when given.

        ADR 004 section 4: a source's authority is the best tier between the
        institution owning its domain and the allowlists. A missing file is empty.
        """
        directory = Path(directory)
        institutions = _institution_domains(registry)
        return cls(
            blocked=_Rules.read(directory / "blocklist.txt"),
            tier1=_Rules.read(directory / "allowlist_tier1.txt").union(institutions[1]),
            tier2=_Rules.read(directory / "allowlist_tier2.txt").union(institutions[2]),
            paywalled=_Rules.read(directory / "paywall.txt"),
        )

    def tier(self, url: str) -> DomainTier:
        """The blocklist wins over both allowlists; a URL without a host is blocked."""
        labels = _labels(url)
        if not labels or self.blocked.match(labels):
            return DomainTier.BLOCKED
        if self.tier1.match(labels):
            return DomainTier.TIER1
        if self.tier2.match(labels):
            return DomainTier.TIER2
        return DomainTier.OTHER

    def is_paywalled(self, url: str) -> bool:
        labels = _labels(url)
        return bool(labels) and self.paywalled.match(labels)


def _institution_domains(registry: str | Path | None) -> dict[int, frozenset[str]]:
    """Domains of the registry's tier 1 and tier 2 institutions; tier 3 earns nothing."""
    found: dict[int, set[str]] = {1: set(), 2: set()}
    if registry is not None and Path(registry).is_file():
        with Path(registry).open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                domain = row["domain"].casefold().strip(".")
                if domain and int(row["tier"]) in found:
                    found[int(row["tier"])].add(domain)
    return {tier: frozenset(domains) for tier, domains in found.items()}


@lru_cache(maxsize=1)
def default_policy() -> DomainPolicy:
    """The shipped lists and registry, read once per process (restart to pick up edits)."""
    return DomainPolicy.load(registry=DEFAULT_REGISTRY)


def domain_tier(url: str) -> DomainTier:
    return default_policy().tier(url)
