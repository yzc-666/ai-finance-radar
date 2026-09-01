#!/usr/bin/env python3
"""Validate Radar envelopes, provenance, source gates, and content hashes."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

try:
    from crawl import (
        EVENT_TYPES,
        SECTORS,
        _is_primary,
        _is_secondary,
        canonicalize_url,
        content_hash,
        domain_allowed,
        parse_datetime,
        publication_gate,
        title_key,
    )
except ImportError:
    from scripts.crawl import (  # type: ignore
        EVENT_TYPES,
        SECTORS,
        _is_primary,
        _is_secondary,
        canonicalize_url,
        content_hash,
        domain_allowed,
        parse_datetime,
        publication_gate,
        title_key,
    )


ROOT = Path(__file__).resolve().parents[1]
SAFE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CJK = re.compile(
    "[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)


@dataclasses.dataclass(frozen=True)
class Issue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class Checker:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.urls: set[str] = set()

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue(path, message))

    def fields(self, value: Any, fields: Sequence[str], path: str) -> bool:
        if not isinstance(value, Mapping):
            self.error(path, "must be an object")
            return False
        for field in fields:
            if field not in value:
                self.error(f"{path}.{field}", "required field is missing")
        return True

    def timestamp(self, value: Any, path: str) -> None:
        if not isinstance(value, str) or parse_datetime(value) is None:
            self.error(path, "must be a valid ISO date-time")
        elif not (value.endswith("Z") or re.search(r"[+-]\d{2}:\d{2}$", value)):
            self.error(path, "must include a UTC offset")

    def date(self, value: Any, path: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            self.error(path, "must be an ISO date")
            return
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            self.error(path, "is not a real date")

    def url(self, value: Any, path: str) -> str:
        canonical = canonicalize_url(value)
        if not canonical.startswith("https://"):
            self.error(path, "must be an absolute HTTPS URL")
        elif canonical:
            self.urls.add(canonical)
        return canonical

    def english(self, value: Any, path: str) -> None:
        if not isinstance(value, str) or not value.strip():
            self.error(path, "must be a non-empty string")
        elif CJK.search(value):
            self.error(path, "must be English-only for this MVP")

    def strings(
        self, value: Any, path: str, *, empty: bool = False
    ) -> list[str]:
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            self.error(path, "must be an array of non-empty strings")
            return []
        if not empty and not value:
            self.error(path, "must not be empty")
        if len(value) != len(set(value)):
            self.error(path, "must not contain duplicates")
        return value


def _load(path: Path, check: Checker, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        check.error(label, f"missing file: {path}")
    except UnicodeDecodeError:
        check.error(label, "must be UTF-8")
    except json.JSONDecodeError as exc:
        check.error(label, f"invalid JSON at line {exc.lineno}, column {exc.colno}")
    return {}


def _records(payload: Any, key: str, check: Checker) -> list[Any]:
    if not check.fields(payload, ("schema_version", "updated_at", key), key):
        return []
    assert isinstance(payload, Mapping)
    if not isinstance(payload.get("schema_version"), str) or not re.fullmatch(
        r"\d+\.\d+\.\d+", payload.get("schema_version", "")
    ):
        check.error(f"{key}.schema_version", "must use X.Y.Z")
    check.timestamp(payload.get("updated_at"), f"{key}.updated_at")
    records = payload.get(key)
    if not isinstance(records, list):
        check.error(key, "collection must be an array")
        return []
    return records


def _config(
    payload: Any, check: Checker
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if not isinstance(payload, Mapping):
        check.error("config", "must be an object")
        return {}, {}
    if payload.get("language") != "en":
        check.error("config.language", "must be 'en'")
    if payload.get("markets") != ["CN", "US"]:
        check.error("config.markets", "must cover exactly CN and US")
    check.timestamp(payload.get("updated_at"), "config.updated_at")
    check.timestamp(
        payload.get("offline_retrieved_at"), "config.offline_retrieved_at"
    )
    taxonomy = payload.get("taxonomy")
    if not isinstance(taxonomy, Mapping):
        check.error("config.taxonomy", "must be an object")
    else:
        if taxonomy.get("sectors") != list(SECTORS):
            check.error("config.taxonomy.sectors", "does not match the schema")
        if set(taxonomy.get("event_types", [])) != set(EVENT_TYPES):
            check.error("config.taxonomy.event_types", "does not match the schema")
    policy = payload.get("policy")
    if not isinstance(policy, Mapping) or (
        policy.get("auto_publish_tiers") != ["primary"]
        or policy.get("candidate_tiers") != ["secondary"]
        or policy.get("secondary_never_auto_publishes") is not True
        or policy.get("commercial_or_paywalled_scraping") is not False
    ):
        check.error("config.policy", "violates publication or scraping policy")
    domains: dict[str, Mapping[str, Any]] = {}
    for index, entry in enumerate(payload.get("official_domains", [])):
        path = f"config.official_domains[{index}]"
        if not isinstance(entry, Mapping):
            check.error(path, "must be an object")
            continue
        domain = str(entry.get("domain", "")).casefold().strip(".")
        if not domain or "/" in domain:
            check.error(f"{path}.domain", "must be a bare DNS domain")
        elif domain in domains:
            check.error(f"{path}.domain", "duplicate domain")
        else:
            domains[domain] = entry
    sources: dict[str, Mapping[str, Any]] = {}
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        check.error("config.sources", "must be an array")
        return sources, domains
    required = (
        "id", "name", "publisher", "source_class", "source_tier",
        "auto_publish", "publish_mode", "enabled", "canonical_url",
        "allowed_domains", "company_ids", "country", "jurisdictions", "sectors",
    )
    for index, source in enumerate(raw_sources):
        path = f"config.sources[{index}]"
        if not check.fields(source, required, path) or not isinstance(source, Mapping):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not SAFE_ID.fullmatch(source_id):
            check.error(f"{path}.id", "must be lowercase kebab-case")
            continue
        if source_id in sources:
            check.error(f"{path}.id", "duplicate source ID")
        sources[source_id] = source
        tier, mode = source.get("source_tier"), source.get("publish_mode")
        if tier == "secondary":
            if source.get("auto_publish") is not False or mode != "candidate":
                check.error(path, "secondary sources must be candidate-only")
        elif tier == "primary":
            if source.get("auto_publish") is not True or mode != "auto":
                check.error(path, "primary automatic sources must use the auto gate")
        else:
            check.error(f"{path}.source_tier", "must be primary or secondary")
        if source.get("auto_publish") and (
            _is_secondary(source) or not _is_primary(source)
        ):
            check.error(f"{path}.auto_publish", "secondary sources cannot auto-publish")
        check.url(source.get("canonical_url"), f"{path}.canonical_url")
        allowed = check.strings(source.get("allowed_domains"), f"{path}.allowed_domains")
        if not domain_allowed(str(source.get("canonical_url", "")), allowed):
            check.error(f"{path}.canonical_url", "outside source domain allowlist")
        if source.get("source_tier") == "primary":
            for domain in allowed:
                if domain not in domains:
                    check.error(
                        f"{path}.allowed_domains",
                        f"{domain!r} is not in official_domains",
                    )
        if source.get("country") not in {"CN", "US"}:
            check.error(f"{path}.country", "must be CN or US")
        check.strings(source.get("jurisdictions"), f"{path}.jurisdictions")
        sectors = check.strings(source.get("sectors"), f"{path}.sectors")
        for sector in sectors:
            if sector not in SECTORS:
                check.error(f"{path}.sectors", f"unsupported sector {sector!r}")
    return sources, domains


def _domain_record(
    url: str, domains: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    host = urlsplit(url).hostname or ""
    matches = [
        (domain, entry)
        for domain, entry in domains.items()
        if host == domain or host.endswith(f".{domain}")
    ]
    return max(matches, key=lambda item: len(item[0]))[1] if matches else None


def _companies(
    records: Sequence[Any],
    domains: Mapping[str, Mapping[str, Any]],
    check: Checker,
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    slugs: set[str] = set()
    product_ids: set[str] = set()
    countries: set[str] = set()
    required = (
        "id", "slug", "name", "country", "hq", "founded_year", "sectors",
        "one_liner", "homepage", "products", "sources",
        "verification_status", "last_verified_at",
    )
    for index, company in enumerate(records):
        path = f"companies[{index}]"
        if not check.fields(company, required, path) or not isinstance(company, Mapping):
            continue
        company_id, slug = company.get("id"), company.get("slug")
        if not isinstance(company_id, str) or not SAFE_ID.fullmatch(company_id):
            check.error(f"{path}.id", "must be lowercase kebab-case")
        elif company_id in result:
            check.error(f"{path}.id", "duplicate company ID")
        else:
            result[company_id] = company
        if not isinstance(slug, str) or not SAFE_ID.fullmatch(slug):
            check.error(f"{path}.slug", "must be lowercase kebab-case")
        elif slug in slugs:
            check.error(f"{path}.slug", "duplicate company slug")
        slugs.add(str(slug))
        if company_id != slug:
            check.error(f"{path}.slug", "must equal company ID")
        if company.get("country") not in {"CN", "US"}:
            check.error(f"{path}.country", "must be CN or US")
        else:
            countries.add(str(company.get("country")))
        check.english(company.get("name"), f"{path}.name")
        check.english(company.get("hq"), f"{path}.hq")
        check.english(company.get("one_liner"), f"{path}.one_liner")
        founded = company.get("founded_year")
        if founded is not None and (
            not isinstance(founded, int)
            or isinstance(founded, bool)
            or not 1800 <= founded <= dt.datetime.now().year
        ):
            check.error(f"{path}.founded_year", "must be null or a plausible year")
        sectors = check.strings(company.get("sectors"), f"{path}.sectors")
        for sector in sectors:
            if sector not in SECTORS:
                check.error(f"{path}.sectors", f"unsupported sector {sector!r}")
        homepage = check.url(company.get("homepage"), f"{path}.homepage")
        registry = _domain_record(homepage, domains)
        if registry is None or company_id not in registry.get("company_ids", []):
            check.error(f"{path}.homepage", "domain is not allowlisted for this company")
        check.timestamp(company.get("last_verified_at"), f"{path}.last_verified_at")
        if company.get("verification_status") != "verified":
            check.error(f"{path}.verification_status", "must be verified")
        products = company.get("products")
        if not isinstance(products, list) or not products:
            check.error(f"{path}.products", "must be a non-empty array")
        else:
            for product_index, product in enumerate(products):
                product_path = f"{path}.products[{product_index}]"
                check.fields(product, ("id", "name", "note", "url"), product_path)
                if isinstance(product, Mapping):
                    product_id = product.get("id")
                    if not isinstance(product_id, str) or not SAFE_ID.fullmatch(product_id):
                        check.error(f"{product_path}.id", "must be lowercase kebab-case")
                    elif product_id in product_ids:
                        check.error(f"{product_path}.id", "duplicate product ID")
                    product_ids.add(str(product_id))
                    check.english(product.get("name"), f"{product_path}.name")
                    check.english(product.get("note"), f"{product_path}.note")
                    product_url = check.url(product.get("url"), f"{product_path}.url")
                    registry = _domain_record(product_url, domains)
                    if registry is None or company_id not in registry.get("company_ids", []):
                        check.error(
                            f"{product_path}.url",
                            "domain is not allowlisted for this company",
                        )
        provenance = company.get("sources")
        if not isinstance(provenance, list) or not provenance:
            check.error(f"{path}.sources", "must contain primary provenance")
        else:
            for source_index, source in enumerate(provenance):
                source_path = f"{path}.sources[{source_index}]"
                check.fields(
                    source, ("url", "publisher", "tier", "retrieved_at", "note"), source_path
                )
                if isinstance(source, Mapping):
                    source_url = check.url(source.get("url"), f"{source_path}.url")
                    check.timestamp(source.get("retrieved_at"), f"{source_path}.retrieved_at")
                    check.english(source.get("publisher"), f"{source_path}.publisher")
                    check.english(source.get("note"), f"{source_path}.note")
                    if source.get("tier") != "primary":
                        check.error(f"{source_path}.tier", "must be primary")
                    registry = _domain_record(source_url, domains)
                    if registry is None or company_id not in registry.get("company_ids", []):
                        check.error(
                            f"{source_path}.url",
                            "domain is not allowlisted for this company",
                        )
    return result


def _confidence(record: Mapping[str, Any], check: Checker, path: str) -> None:
    """Validate confidence when present (legacy and future schema compatible)."""
    if "confidence" not in record:
        return
    confidence = record["confidence"]
    score = confidence.get("score") if isinstance(confidence, Mapping) else confidence
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(float(score))
        or not 0 <= float(score) <= 1
    ):
        check.error(f"{path}.confidence", "must be a finite number between 0 and 1")


def _events(
    records: Sequence[Any],
    companies: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    check: Checker,
) -> tuple[set[str], set[str]]:
    ids, urls, signatures = set(), set(), set()
    required = (
        "id", "slug", "type", "title", "company_ids", "country", "sectors",
        "event_date", "published_at", "summary", "primary_url", "publisher",
        "source_id", "source_tier", "retrieved_at", "verification_status",
        "provenance", "content_hash",
    )
    for index, event in enumerate(records):
        path = f"events[{index}]"
        if not check.fields(event, required, path) or not isinstance(event, Mapping):
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.startswith("evt-") or not SAFE_ID.fullmatch(event_id):
            check.error(f"{path}.id", "must be a safe evt- ID")
        elif event_id in ids:
            check.error(f"{path}.id", "duplicate event ID")
        ids.add(str(event_id))
        if event.get("type") not in EVENT_TYPES:
            check.error(f"{path}.type", "unsupported event type")
        if event.get("country") not in {"CN", "US"}:
            check.error(f"{path}.country", "must be CN or US")
        references = check.strings(event.get("company_ids"), f"{path}.company_ids", empty=True)
        if event.get("type") != "regulation" and not references:
            check.error(f"{path}.company_ids", "only regulation events may be market-wide")
        for company_id in references:
            if company_id not in companies:
                check.error(f"{path}.company_ids", f"references unknown company {company_id!r}")
            elif companies[company_id].get("country") != event.get("country"):
                check.error(f"{path}.company_ids", f"{company_id!r} does not match event country")
        sectors = check.strings(event.get("sectors"), f"{path}.sectors")
        for sector in sectors:
            if sector not in SECTORS:
                check.error(f"{path}.sectors", f"unsupported sector {sector!r}")
        company_sectors = {
            sector
            for company_id in references
            for sector in companies.get(company_id, {}).get("sectors", [])
        }
        if references and not company_sectors.intersection(sectors):
            check.error(f"{path}.sectors", "must overlap referenced company sectors")
        check.date(event.get("event_date"), f"{path}.event_date")
        check.timestamp(event.get("published_at"), f"{path}.published_at")
        check.timestamp(event.get("retrieved_at"), f"{path}.retrieved_at")
        published = parse_datetime(event.get("published_at"))
        retrieved = parse_datetime(event.get("retrieved_at"))
        if published and retrieved and retrieved < published:
            check.error(f"{path}.retrieved_at", "cannot predate publication")
        check.english(event.get("title"), f"{path}.title")
        check.english(event.get("summary"), f"{path}.summary")
        check.english(event.get("publisher"), f"{path}.publisher")
        if event.get("context") is not None:
            check.english(event.get("context"), f"{path}.context")
            if event.get("context") == event.get("summary"):
                check.error(f"{path}.context", "must be separate from summary")
        url = check.url(event.get("primary_url"), f"{path}.primary_url")
        source = sources.get(str(event.get("source_id", "")))
        if source is None:
            check.error(f"{path}.source_id", "unknown source")
        else:
            allowed, reason = publication_gate(source, url)
            if not allowed:
                check.error(path, f"event fails auto-publication gate: {reason}")
            if event.get("publisher") != source.get("publisher"):
                check.error(f"{path}.publisher", "must match source registry")
        if event.get("source_tier") != "primary":
            check.error(f"{path}.source_tier", "must be primary")
        if event.get("verification_status") != "verified":
            check.error(f"{path}.verification_status", "must be verified")
        provenance = event.get("provenance")
        if not isinstance(provenance, list) or not provenance:
            check.error(f"{path}.provenance", "must be a non-empty array")
        else:
            for provenance_index, item in enumerate(provenance):
                item_path = f"{path}.provenance[{provenance_index}]"
                check.fields(
                    item, ("source_id", "url", "publisher", "source_tier", "retrieved_at"), item_path
                )
                if isinstance(item, Mapping):
                    provenance_url = check.url(item.get("url"), f"{item_path}.url")
                    check.timestamp(item.get("retrieved_at"), f"{item_path}.retrieved_at")
                    if item.get("source_tier") != "primary":
                        check.error(f"{item_path}.source_tier", "must be primary")
                    if (
                        provenance_url == url
                        and item.get("source_id") == event.get("source_id")
                    ):
                        pass
            if not any(
                isinstance(item, Mapping)
                and canonicalize_url(item.get("url")) == url
                and item.get("source_id") == event.get("source_id")
                for item in provenance
            ):
                check.error(
                    f"{path}.provenance",
                    "must include the primary URL and source ID",
                )
        digest = event.get("content_hash")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            check.error(f"{path}.content_hash", "must be a lowercase SHA-256 digest")
        _confidence(event, check, path)
        signature = (title_key(event.get("title")), str(event.get("event_date", "")))
        if url in urls:
            check.error(f"{path}.primary_url", "duplicate canonical URL")
        if signature in signatures:
            check.error(path, "duplicate normalized title/date")
        urls.add(url)
        signatures.add(signature)
    return ids, urls


def _candidates(
    records: Sequence[Any],
    companies: Mapping[str, Any],
    sources: Mapping[str, Mapping[str, Any]],
    event_urls: set[str],
    check: Checker,
) -> None:
    ids, urls, signatures = set(), set(), set()
    required = (
        "id", "slug", "type", "title", "company_ids", "country", "sectors",
        "event_date", "published_at", "summary", "discovery_url", "publisher",
        "source_id", "source_tier", "retrieved_at", "verification_status",
        "verification_notes", "content_hash",
    )
    for index, candidate in enumerate(records):
        path = f"candidates[{index}]"
        if not check.fields(candidate, required, path) or not isinstance(candidate, Mapping):
            continue
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id.startswith("cand-") or not SAFE_ID.fullmatch(candidate_id):
            check.error(f"{path}.id", "must be a safe cand- ID")
        elif candidate_id in ids:
            check.error(f"{path}.id", "duplicate candidate ID")
        ids.add(str(candidate_id))
        if candidate.get("type") not in EVENT_TYPES:
            check.error(f"{path}.type", "unsupported event type")
        if candidate.get("country") not in {"CN", "US"}:
            check.error(f"{path}.country", "must be CN or US")
        for company_id in check.strings(
            candidate.get("company_ids"), f"{path}.company_ids", empty=True
        ):
            if company_id not in companies:
                check.error(f"{path}.company_ids", f"references unknown company {company_id!r}")
        sectors = check.strings(candidate.get("sectors"), f"{path}.sectors")
        for sector in sectors:
            if sector not in SECTORS:
                check.error(f"{path}.sectors", f"unsupported sector {sector!r}")
        check.date(candidate.get("event_date"), f"{path}.event_date")
        check.timestamp(candidate.get("published_at"), f"{path}.published_at")
        check.timestamp(candidate.get("retrieved_at"), f"{path}.retrieved_at")
        published = parse_datetime(candidate.get("published_at"))
        retrieved = parse_datetime(candidate.get("retrieved_at"))
        if published and retrieved and retrieved < published:
            check.error(f"{path}.retrieved_at", "cannot predate publication")
        check.english(candidate.get("title"), f"{path}.title")
        check.english(candidate.get("summary"), f"{path}.summary")
        check.english(candidate.get("publisher"), f"{path}.publisher")
        check.english(
            candidate.get("verification_notes"),
            f"{path}.verification_notes",
        )
        url = check.url(candidate.get("discovery_url"), f"{path}.discovery_url")
        source = sources.get(str(candidate.get("source_id", "")))
        if source is None:
            check.error(f"{path}.source_id", "unknown source")
        elif source.get("source_tier") != "secondary" or source.get("publish_mode") != "candidate":
            check.error(f"{path}.source_id", "candidate must come from a secondary source")
        else:
            if candidate.get("publisher") != source.get("publisher"):
                check.error(f"{path}.publisher", "must match source registry")
            if not domain_allowed(url, source.get("allowed_domains", [])):
                check.error(f"{path}.discovery_url", "outside source domain allowlist")
        if candidate.get("source_tier") != "secondary" or candidate.get("verification_status") != "unverified":
            check.error(path, "candidate must remain secondary and unverified")
        digest = candidate.get("content_hash")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            check.error(f"{path}.content_hash", "must be a lowercase SHA-256 digest")
        _confidence(candidate, check, path)
        if url in urls:
            check.error(f"{path}.discovery_url", "duplicate candidate URL")
        if url in event_urls:
            check.error(f"{path}.discovery_url", "also appears in verified events")
        signature = (
            title_key(candidate.get("title")),
            str(candidate.get("event_date", "")),
        )
        if signature in signatures:
            check.error(path, "duplicate normalized title/date")
        urls.add(url)
        signatures.add(signature)


def _cross_dataset(
    events: Sequence[Any], candidates: Sequence[Any], check: Checker
) -> None:
    event_ids = {
        str(event.get("id"))
        for event in events
        if isinstance(event, Mapping)
    }
    event_signatures = {
        (title_key(event.get("title")), str(event.get("event_date", "")))
        for event in events
        if isinstance(event, Mapping)
    }
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        path = f"candidates[{index}]"
        if str(candidate.get("id")) in event_ids:
            check.error(path, "candidate ID also appears in verified events")
        if (
            title_key(candidate.get("title")),
            str(candidate.get("event_date", "")),
        ) in event_signatures:
            check.error(path, "candidate title/date also appears in verified events")


def _probe_url(url: str, timeout: float) -> str | None:
    headers = {"User-Agent": "AI-Finance-Radar-Link-Check/1.0", "Accept": "*/*"}
    try:
        request = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return None if response.status < 400 else f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        if error.code not in {403, 405}:
            return f"HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return str(error)
    try:
        request = urllib.request.Request(
            url,
            headers={**headers, "Range": "bytes=0-0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
            return None if response.status < 400 else f"HTTP {response.status}"
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return str(error)


def _check_links(urls: Iterable[str], timeout: float) -> list[Issue]:
    issues = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_probe_url, url, timeout): url
            for url in sorted(set(urls))
        }
        for future in as_completed(futures):
            message = future.result()
            if message:
                issues.append(Issue(f"link[{futures[future]}]", message))
    return sorted(issues, key=lambda issue: (issue.path, issue.message))


@dataclasses.dataclass
class Report:
    issues: list[Issue]
    source_count: int
    company_count: int
    event_count: int
    candidate_count: int

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_repository(
    root: Path = ROOT,
    *,
    check_links: bool = False,
    link_timeout: float = 8,
) -> Report:
    check = Checker()
    config = _load(root / "config/sources.json", check, "config")
    companies_payload = _load(root / "data/companies.json", check, "companies")
    events_payload = _load(root / "data/events.json", check, "events")
    candidates_payload = _load(root / "data/candidates.json", check, "candidates")
    sources, domains = _config(config, check)
    company_records = _records(companies_payload, "companies", check)
    event_records = _records(events_payload, "events", check)
    candidate_records = _records(candidates_payload, "candidates", check)
    companies = _companies(company_records, domains, check)
    for source_id, source in sources.items():
        for company_id in source.get("company_ids", []):
            if company_id not in companies:
                check.error(
                    f"source[{source_id}].company_ids",
                    f"references unknown company {company_id!r}",
                )
    for domain, entry in domains.items():
        for company_id in entry.get("company_ids", []):
            if company_id not in companies:
                check.error(
                    f"official_domain[{domain}].company_ids",
                    f"references unknown company {company_id!r}",
                )
    _, event_urls = _events(event_records, companies, sources, check)
    _candidates(candidate_records, companies, sources, event_urls, check)
    _cross_dataset(event_records, candidate_records, check)
    if check_links:
        check.issues.extend(_check_links(check.urls, link_timeout))
    return Report(
        check.issues,
        len(sources),
        len(company_records),
        len(event_records),
        len(candidate_records),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--check-links", action="store_true")
    parser.add_argument("--link-timeout", type=float, default=8)
    args = parser.parse_args(argv)
    report = validate_repository(
        args.root.resolve(),
        check_links=args.check_links,
        link_timeout=args.link_timeout,
    )
    if report.issues:
        for issue in report.issues:
            print(f"ERROR {issue}", file=sys.stderr)
        print(f"Validation failed with {len(report.issues)} error(s).", file=sys.stderr)
        return 1
    if not args.quiet:
        print(
            f"Validation passed: {report.company_count} companies, {report.event_count} events, "
            f"{report.candidate_count} candidates, {report.source_count} sources."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
