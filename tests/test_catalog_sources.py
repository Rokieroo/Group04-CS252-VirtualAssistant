"""ADR 004: the catalog source registry stays lawful and matches the ADR table."""

import re
from datetime import date
from pathlib import Path

import pytest
import yaml

from app.vetting.policy import DomainTier, default_policy

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = yaml.safe_load((ROOT / "data/policy/catalog_sources.yaml").read_text(encoding="utf-8"))
ADR = (ROOT / "docs/adr/004-verified-catalog.md").read_text(encoding="utf-8")
LICENSES = REGISTRY["licenses"]
PROVIDERS = REGISTRY["providers"]
REQUIRED = {"id", "name", "use", "levels", "domains", "license", "method", "endpoint",
            "automated", "rate_limit_per_sec", "attribution", "evidence", "checked_on"}


def provider_licenses(provider: dict) -> list[str]:
    if provider["license"] == "per_item":
        return provider.get("item_licenses") or []
    return [provider["license"]]


@pytest.mark.parametrize("license_id", sorted(LICENSES))
def test_only_reusable_licenses_allow_verbatim_items(license_id):
    # spec 12.2: exercises are stored word for word only under CC0 / BY / BY-SA terms.
    restricted = "-NC" in license_id or "-ND" in license_id or license_id == "ALL-RIGHTS-RESERVED"
    assert LICENSES[license_id]["verbatim"] is not restricted


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p["id"])
def test_provider_entry_is_complete_and_lawful(provider):
    assert REQUIRED <= provider.keys()
    assert provider["use"] in {"source", "authority"}
    assert provider["method"] in {"api", "sitemap", "manual"}
    assert set(provider["levels"]) <= {"k12", "undergrad", "grad"}
    licenses = provider_licenses(provider)
    assert licenses, "per_item providers must list item_licenses"
    assert set(licenses) <= LICENSES.keys()
    if provider["automated"]:
        assert provider["rate_limit_per_sec"] > 0
    else:
        # Terms or a bot challenge forbid automated access: no connector, no rate.
        assert provider["method"] == "manual"
        assert provider["rate_limit_per_sec"] is None
    assert provider["evidence"].startswith("https://")
    assert isinstance(provider["checked_on"], date)


@pytest.mark.parametrize("provider", PROVIDERS, ids=lambda p: p["id"])
def test_provider_domains_pass_the_domain_policy(provider):
    policy = default_policy()
    for domain in provider["domains"]:
        assert domain == domain.lower().strip(".")
        url = f"https://{domain}/"
        assert policy.tier(url) is not DomainTier.BLOCKED
        assert not policy.is_paywalled(url)


def test_ids_are_unique():
    ids = [provider["id"] for provider in PROVIDERS]
    assert len(ids) == len(set(ids))


def test_adr_table_lists_exactly_the_registry_providers():
    in_adr = set(re.findall(r"^\| `([a-z0-9_]+)` \|", ADR, flags=re.MULTILINE))
    assert in_adr == {provider["id"] for provider in PROVIDERS}
