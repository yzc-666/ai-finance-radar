#!/usr/bin/env python3
"""Provenance-first, source-gated ingestion for AI × Finance Radar."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime as dt
import email.utils
import hashlib
import json
import logging
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("radar.crawl")
USER_AGENT = (
    "AI-Finance-Radar/1.0 "
    "(https://github.com/yzc-666/ai-finance-radar; contact via repository issues)"
)
EVENT_TYPES = {
    "funding",
    "product",
    "partnership",
    "customer",
    "acquisition",
    "regulation",
}
SECTORS = (
    "Research & Data",
    "Trading & Wealth",
    "Banking Operations",
    "Credit & Underwriting",
    "Fraud & Identity",
    "AML/KYC & Compliance",
    "Insurance",
    "Customer Operations",
    "Financial Infrastructure",
)
SUPPORTED_ADAPTERS = {
    "rss",
    "atom",
    "feed",
    "federal-register",
    "sec-submissions",
    "sec-companyfacts",
}
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}
MAX_BYTES = 12 * 1024 * 1024


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_datetime(value: dt.datetime) -> str:
    return (
        value.astimezone(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_datetime(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, dt.date):
        parsed = dt.datetime.combine(value, dt.time.min)
    else:
        text = str(value).strip()
        try:
            parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = email.utils.parsedate_to_datetime(text)
            except (TypeError, ValueError, OverflowError):
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def clean_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_key(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", clean_text(value).casefold()).strip()


def slug(value: Any, fallback: str = "record") -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    result = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return result or fallback


def canonicalize_url(value: Any) -> str:
    text = clean_text(value)
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    try:
        host = parts.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parts.port
    except (UnicodeError, ValueError):
        return ""
    scheme = parts.scheme.lower()
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = []
    for key, item in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in TRACKING_KEYS:
            continue
        query.append((key, item))
    return urllib.parse.urlunsplit(
        (scheme, netloc, path, urllib.parse.urlencode(sorted(query)), "")
    )


def json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_hash(record: Mapping[str, Any]) -> str:
    """Hash semantic fields while ignoring retrieval/provenance transport data."""
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"content_hash", "provenance", "retrieved_at"}
    }
    return json_sha256(payload)


def normalized_title(value: Any) -> str:
    return title_key(value)


def canonical_event_sha256(event: Mapping[str, Any]) -> str:
    payload = dict(event)
    payload.pop("sha256", None)
    return json_sha256(payload)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _source_class(source: Mapping[str, Any]) -> str:
    return clean_text(source.get("source_class") or source.get("source_tier")).casefold()


def _is_secondary(source: Mapping[str, Any]) -> bool:
    value = _source_class(source)
    return any(term in value for term in ("secondary", "news", "media", "tier-c"))


def _is_primary(source: Mapping[str, Any]) -> bool:
    value = _source_class(source)
    return not _is_secondary(source) and any(
        term in value
        for term in ("primary", "government", "regulator", "official", "company", "sro")
    )


def allowed_domains(source: Mapping[str, Any]) -> list[str]:
    configured = [
        clean_text(item).casefold().rstrip(".")
        for item in _list(source.get("allowed_domains"))
        if clean_text(item)
    ]
    if configured:
        return configured
    canonical = canonicalize_url(source.get("canonical_url"))
    host = urllib.parse.urlsplit(canonical).hostname if canonical else ""
    if host:
        return [host.removeprefix("www.")]
    return []


def domain_allowed(url: str, domains: Sequence[str]) -> bool:
    canonical = canonicalize_url(url)
    host = (urllib.parse.urlsplit(canonical).hostname or "").casefold()
    for raw in domains:
        pattern = raw.casefold().rstrip(".")
        if pattern.startswith("*.") and host.endswith(f".{pattern[2:]}"):
            return True
        if host == pattern or host.endswith(f".{pattern}"):
            return True
    return False


host_is_allowed = domain_allowed


def publication_gate(source: Mapping[str, Any], evidence_url: str) -> tuple[bool, str]:
    if _is_secondary(source):
        return False, "secondary sources are discovery-only"
    if not _is_primary(source):
        return False, "source class is not primary"
    if source.get("auto_publish") is not True:
        return False, "source is not approved for automatic publication"
    domains = allowed_domains(source)
    if not domains:
        return False, "source has no domain allowlist"
    canonical = canonicalize_url(evidence_url)
    if not canonical or not domain_allowed(canonical, domains):
        return False, "evidence URL is outside the source domain allowlist"
    if not canonical.startswith("https://"):
        return False, "published evidence must use HTTPS"
    return True, "allowlisted primary source"


def infer_event_type(title: str, summary: str, fallback: str = "product") -> str:
    text = f"{title} {summary}".casefold()
    rules = (
        ("acquisition", ("acquire", "acquisition", "buys ")),
        ("funding", ("raises ", "raised ", "funding", "financing", "series ")),
        ("customer", ("selects ", "selected ", "chooses ", "deploys ", "adopts ")),
        ("partnership", ("partner", "collaborat", "integrates ", "joins forces")),
        ("regulation", ("regulator", "regulation", "rulemaking", "enforcement", "task force", "filing")),
        ("product", ("launch", "unveil", "introduc", "release", "new platform")),
    )
    for event_type, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return event_type
    return fallback if fallback in EVENT_TYPES else "product"


def machine_details(source: Mapping[str, Any]) -> tuple[str, str, Mapping[str, Any]]:
    machine = source.get("machine_endpoint")
    options: Mapping[str, Any] = machine if isinstance(machine, Mapping) else {}
    adapter = clean_text(
        options.get("adapter")
        or options.get("type")
        or source.get("adapter")
        or source.get("adapter_type")
    ).casefold().replace("_", "-")
    aliases = {
        "rss-atom": "feed",
        "federal-register-api": "federal-register",
        "federalregister": "federal-register",
        "sec-edgar": "sec-submissions",
        "sec-edgar-submissions": "sec-submissions",
        "sec-company-facts": "sec-companyfacts",
        "sec-edgar-companyfacts": "sec-companyfacts",
        "discovery-rss": "rss",
    }
    adapter = aliases.get(adapter, adapter)
    if isinstance(machine, str):
        endpoint = machine
    else:
        endpoint = clean_text(
            options.get("url")
            or options.get("endpoint")
            or source.get("feed_url")
            or source.get("api_url")
            or source.get("endpoint")
        )
    return adapter, endpoint, options


@dataclasses.dataclass(frozen=True)
class HttpResult:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = USER_AGENT,
        timeout: float = 30,
        retries: int = 3,
        opener: Any = urllib.request.urlopen,
        sleeper: Any = time.sleep,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.opener = opener
        self.sleeper = sleeper
        self.last_request: dict[str, float] = {}

    def _delay(self, source: Mapping[str, Any]) -> None:
        source_id = clean_text(source.get("id")) or "source"
        machine = source.get("machine_endpoint")
        configured = machine.get("delay_seconds") if isinstance(machine, Mapping) else None
        rate = source.get("rate_limit")
        if configured is None and isinstance(rate, Mapping):
            per_minute = rate.get("requests_per_minute")
            if isinstance(per_minute, (int, float)) and per_minute > 0:
                configured = 60 / float(per_minute)
        delay = max(0.0, float(configured if configured is not None else 1.0))
        elapsed = time.monotonic() - self.last_request.get(source_id, 0)
        if elapsed < delay:
            self.sleeper(delay - elapsed)
        self.last_request[source_id] = time.monotonic()

    def get(
        self,
        url: str,
        source: Mapping[str, Any],
        conditional: Mapping[str, Any] | None = None,
    ) -> HttpResult:
        endpoint = canonicalize_url(url)
        if not endpoint or not endpoint.startswith("https://"):
            raise ValueError("machine endpoint must be an absolute HTTPS URL")
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9",
            "Accept-Encoding": "identity",
        }
        if conditional and conditional.get("etag"):
            headers["If-None-Match"] = str(conditional["etag"])
        if conditional and conditional.get("last_modified"):
            headers["If-Modified-Since"] = str(conditional["last_modified"])
        for attempt in range(self.retries + 1):
            self._delay(source)
            request = urllib.request.Request(endpoint, headers=headers, method="GET")
            try:
                response = self.opener(request, timeout=self.timeout)
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise ValueError("source response is too large")
                return HttpResult(
                    canonicalize_url(response.geturl()) or endpoint,
                    int(getattr(response, "status", response.getcode())),
                    {key.casefold(): value for key, value in response.headers.items()},
                    body,
                )
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    return HttpResult(endpoint, 304, {}, b"")
                retryable = exc.code in {408, 425, 429} or 500 <= exc.code <= 599
                if not retryable or attempt == self.retries:
                    raise
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = min(120.0, max(0.0, float(retry_after)))
                except (TypeError, ValueError):
                    wait = min(30.0, 2.0**attempt)
                self.sleeper(wait)
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise
                self.sleeper(min(30.0, 2.0**attempt))
        raise RuntimeError("unreachable")


class FixtureHttpClient:
    """Offline client that resolves each source's fixture under one directory."""

    def __init__(self, fixture_dir: Path):
        self.fixture_dir = fixture_dir

    def get(
        self,
        url: str,
        source: Mapping[str, Any],
        conditional: Mapping[str, Any] | None = None,
    ) -> HttpResult:
        del conditional
        fixture = clean_text(source.get("fixture"))
        if not fixture:
            raise FileNotFoundError("source has no offline fixture")
        path = self.fixture_dir / fixture
        body = path.read_bytes()
        suffix = path.suffix.casefold()
        content_type = (
            "application/json"
            if suffix == ".json"
            else "application/atom+xml"
            if "atom" in path.name.casefold()
            else "application/rss+xml"
        )
        return HttpResult(
            canonicalize_url(url),
            200,
            {"content-type": content_type},
            body,
        )


@dataclasses.dataclass
class RawItem:
    external_id: str
    title: str
    summary: str
    url: str
    published_at: dt.datetime
    event_type: str
    payload: Any
    publisher: str
    company_ids: list[str]
    country: str
    jurisdictions: list[str]
    sectors: list[str]
    language: str
    http_status: int = 200
    content_type: str = "application/octet-stream"


def _common_item(
    source: Mapping[str, Any],
    options: Mapping[str, Any],
    **values: Any,
) -> RawItem:
    fallback_event_type = values.pop("event_type", "regulation")
    event_type = clean_text(
        options.get("event_type")
        or source.get("default_event_type")
        or fallback_event_type
    )
    if event_type not in EVENT_TYPES:
        event_type = "regulation"
    jurisdictions = [
        clean_text(item)
        for item in _list(
            options.get("jurisdictions")
            or source.get("jurisdictions")
            or source.get("jurisdiction")
        )
        if clean_text(item)
    ]
    sectors = [
        clean_text(item)
        for item in _list(options.get("sectors") or source.get("sectors"))
        if clean_text(item)
    ]
    company_ids = [
        clean_text(item)
        for item in _list(options.get("company_ids") or source.get("company_ids"))
        if clean_text(item)
    ]
    language = clean_text(options.get("language") or source.get("language"))
    if not language:
        language = "zh-CN" if any(item.startswith("CN") for item in jurisdictions) else "en"
    return RawItem(
        event_type=event_type,
        publisher=clean_text(
            source.get("publisher") or source.get("owner") or source.get("name")
        ),
        company_ids=list(dict.fromkeys(company_ids)),
        country=clean_text(source.get("country") or (jurisdictions[0] if jurisdictions else "")),
        jurisdictions=list(dict.fromkeys(jurisdictions)),
        sectors=list(dict.fromkeys(sectors)),
        language=language,
        **values,
    )


def _xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _xml_text(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        if _xml_name(child.tag) in names:
            value = "".join(child.itertext())
            if value.strip():
                return clean_text(value)
    return ""


def parse_feed(
    body: bytes,
    source: Mapping[str, Any],
    options: Mapping[str, Any],
    since: dt.datetime,
) -> list[RawItem]:
    root = ET.fromstring(body)
    records = []
    for entry in root.iter():
        if _xml_name(entry.tag) not in {"item", "entry"}:
            continue
        title = _xml_text(entry, {"title"})
        summary = _xml_text(entry, {"summary", "description", "content", "encoded"})
        published = parse_datetime(
            _xml_text(entry, {"published", "updated", "pubdate", "date"})
        )
        link = ""
        for child in list(entry):
            if _xml_name(child.tag) == "link":
                link = clean_text(child.attrib.get("href") or child.text)
                if link:
                    break
        if not link:
            link = _xml_text(entry, {"link"})
        url = canonicalize_url(link)
        if not title or not url or published is None or published < since:
            continue
        keywords = [clean_text(item).casefold() for item in _list(options.get("keywords") or source.get("include_keywords"))]
        haystack = f"{title} {summary}".casefold()
        if keywords and not any(keyword in haystack for keyword in keywords):
            continue
        records.append(
            _common_item(
                source,
                options,
                external_id=_xml_text(entry, {"guid", "id"}) or url,
                title=title,
                summary=summary or title,
                url=url,
                published_at=published,
                payload={
                    "id": _xml_text(entry, {"guid", "id"}),
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "published_at": iso_datetime(published),
                },
                event_type=infer_event_type(title, summary),
            )
        )
    return records


def parse_federal_register(
    payload: Any,
    source: Mapping[str, Any],
    options: Mapping[str, Any],
    since: dt.datetime,
) -> list[RawItem]:
    results = payload.get("results") if isinstance(payload, Mapping) else None
    if not isinstance(results, list):
        raise ValueError("Federal Register response lacks a results array")
    records = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        published = parse_datetime(item.get("publication_date"))
        title = clean_text(item.get("title"))
        url = canonicalize_url(item.get("html_url") or item.get("raw_text_url"))
        if not title or not url or published is None or published < since:
            continue
        records.append(
            _common_item(
                source,
                options,
                external_id=clean_text(item.get("document_number")) or url,
                title=title,
                summary=clean_text(item.get("abstract")) or title,
                url=url,
                published_at=published,
                payload=item,
                event_type="regulation",
            )
        )
    return records


def _parallel(mapping: Mapping[str, Any], key: str, index: int) -> Any:
    values = mapping.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def parse_sec_submissions(
    payload: Any,
    source: Mapping[str, Any],
    options: Mapping[str, Any],
    since: dt.datetime,
) -> list[RawItem]:
    recent = payload.get("filings", {}).get("recent") if isinstance(payload, Mapping) else None
    if not isinstance(recent, Mapping) or not isinstance(recent.get("accessionNumber"), list):
        raise ValueError("SEC response lacks filings.recent arrays")
    forms = {
        clean_text(item).upper()
        for item in _list(options.get("forms") or source.get("forms") or ["8-K", "D", "D/A"])
    }
    cik = re.sub(r"\D", "", clean_text(payload.get("cik")))
    entity = clean_text(payload.get("name") or source.get("name"))
    records = []
    for index, accession in enumerate(recent["accessionNumber"]):
        form = clean_text(_parallel(recent, "form", index)).upper()
        published = parse_datetime(_parallel(recent, "filingDate", index))
        document = clean_text(_parallel(recent, "primaryDocument", index))
        if form not in forms or published is None or published < since or not cik or not document:
            continue
        accession_text = clean_text(accession)
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession_text.replace('-', '')}/{urllib.parse.quote(document)}"
        )
        description = clean_text(_parallel(recent, "primaryDocDescription", index))
        records.append(
            _common_item(
                source,
                options,
                external_id=accession_text,
                title=f"{entity} filed Form {form} with the SEC",
                summary=description or f"{entity} filed Form {form} with the SEC.",
                url=url,
                published_at=published,
                payload={
                    key: _parallel(recent, key, index)
                    for key in (
                        "accessionNumber",
                        "filingDate",
                        "form",
                        "primaryDocument",
                        "primaryDocDescription",
                    )
                },
                event_type="regulation",
            )
        )
    return records


def parse_sec_companyfacts(
    payload: Any,
    source: Mapping[str, Any],
    options: Mapping[str, Any],
    since: dt.datetime,
) -> list[RawItem]:
    selected = {
        clean_text(item)
        for item in _list(options.get("concepts") or source.get("fact_concepts"))
    }
    if not selected:
        return []
    facts = payload.get("facts") if isinstance(payload, Mapping) else None
    if not isinstance(facts, Mapping):
        raise ValueError("SEC companyfacts response lacks facts")
    entity = clean_text(payload.get("entityName") or source.get("name"))
    cik = re.sub(r"\D", "", clean_text(payload.get("cik")))
    records = []
    for taxonomy, concepts in facts.items():
        if not isinstance(concepts, Mapping):
            continue
        for concept, fact in concepts.items():
            if concept not in selected and f"{taxonomy}:{concept}" not in selected:
                continue
            if not isinstance(fact, Mapping) or not isinstance(fact.get("units"), Mapping):
                continue
            for unit, observations in fact["units"].items():
                if not isinstance(observations, list):
                    continue
                for observation in observations:
                    if not isinstance(observation, Mapping):
                        continue
                    published = parse_datetime(observation.get("filed"))
                    accession = clean_text(observation.get("accn"))
                    if published is None or published < since or not accession or not cik:
                        continue
                    url = (
                        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                        f"{accession.replace('-', '')}/"
                    )
                    label = clean_text(fact.get("label") or concept)
                    records.append(
                        _common_item(
                            source,
                            options,
                            external_id=f"{accession}|{taxonomy}:{concept}|{observation.get('end', '')}",
                            title=f"{entity} reported {label}",
                            summary=f"{entity} reported {label} as {observation.get('val')} {unit} in an SEC filing.",
                            url=url,
                            published_at=published,
                            payload={"taxonomy": taxonomy, "concept": concept, "unit": unit, "fact": observation},
                            event_type="regulation",
                        )
                    )
    return records


def _source_tier(source: Mapping[str, Any]) -> int:
    value = _source_class(source)
    return 1 if any(term in value for term in ("government", "regulator", "official")) else 2


def _clip(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[: maximum - 1].rstrip() + "…"


def normalize_item(
    item: RawItem, source: Mapping[str, Any], retrieved_at: dt.datetime
) -> tuple[str, dict[str, Any]] | None:
    url = canonicalize_url(item.url)
    publish, reason = publication_gate(source, url)
    if publish and (not item.country or not item.sectors):
        publish, reason = False, "required jurisdiction or sector metadata is missing"
    identity = clean_text(item.external_id) or url
    digest = hashlib.sha256(
        f"{source.get('id')}|{identity}".encode("utf-8")
    ).hexdigest()[:16]
    if publish:
        event_date = item.published_at.date().isoformat()
        title = _clip(clean_text(item.title), 300)
        summary = _clip(clean_text(item.summary), 500)
        event: dict[str, Any] = {
            "id": f"evt-{digest}",
            "slug": f"{slug(title)[:72].rstrip('-')}-{digest[:8]}",
            "type": item.event_type,
            "title": title,
            "company_ids": item.company_ids,
            "country": item.country,
            "sectors": item.sectors,
            "event_date": event_date,
            "published_at": iso_datetime(item.published_at),
            "summary": summary or title,
            "primary_url": url,
            "publisher": item.publisher,
            "source_id": clean_text(source.get("id")),
            "source_tier": "primary",
            "retrieved_at": iso_datetime(retrieved_at),
            "verification_status": "verified",
            "provenance": [{
                "source_id": clean_text(source.get("id")),
                "publisher": item.publisher,
                "url": url,
                "source_tier": "primary",
                "retrieved_at": iso_datetime(retrieved_at),
            }],
        }
        event["content_hash"] = content_hash(event)
        return "event", event
    if not _is_secondary(source):
        LOG.info("%s skipped: %s", source.get("id"), reason)
        return None
    candidate = {
        "id": f"cand-{slug(source.get('id'))}-{digest}",
        "slug": f"{slug(item.title)[:72].rstrip('-')}-{digest[:8]}",
        "type": item.event_type,
        "title": _clip(clean_text(item.title), 240),
        "company_ids": item.company_ids,
        "country": item.country,
        "sectors": item.sectors,
        "event_date": item.published_at.date().isoformat(),
        "published_at": iso_datetime(item.published_at),
        "summary": _clip(clean_text(item.summary), 500) or clean_text(item.title),
        "discovery_url": url,
        "publisher": item.publisher,
        "source_id": clean_text(source.get("id")),
        "source_tier": "secondary",
        "retrieved_at": iso_datetime(retrieved_at),
        "verification_status": "unverified",
        "verification_notes": _clip(
            f"{reason}; locate an allowlisted primary source before publication.", 500
        ),
    }
    candidate["content_hash"] = content_hash(candidate)
    return "candidate", candidate


def _request_state(state: MutableMapping[str, Any], url: str) -> MutableMapping[str, Any]:
    requests = state.setdefault("requests", {})
    if not isinstance(requests, MutableMapping):
        requests = {}
        state["requests"] = requests
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    request = requests.setdefault(key, {})
    if not isinstance(request, MutableMapping):
        request = {}
        requests[key] = request
    return request


def _append_query(url: str, additions: Mapping[str, Any]) -> str:
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    present = {key for key, _ in pairs}
    pairs.extend((key, str(value)) for key, value in additions.items() if key not in present)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(pairs), "")
    )


def crawl_source(
    source: Mapping[str, Any],
    client: HttpClient,
    state: MutableMapping[str, Any],
    since: dt.datetime,
    now: dt.datetime,
) -> tuple[list[RawItem], str]:
    adapter, endpoint, options = machine_details(source)
    if not endpoint:
        return [], "skipped-no-machine-endpoint"
    if adapter not in SUPPORTED_ADAPTERS:
        return [], f"skipped-unsupported-adapter:{adapter or 'missing'}"
    if adapter == "federal-register":
        endpoint = _append_query(
            endpoint,
            {
                "per_page": options.get("per_page", 100),
                "order": "newest",
                "conditions[publication_date][gte]": since.date().isoformat(),
            },
        )
    request_state = _request_state(state, endpoint)
    result = client.get(endpoint, source, request_state)
    request_state["last_checked_at"] = iso_datetime(now)
    if result.status == 304:
        return [], "not-modified"
    if not 200 <= result.status <= 299:
        raise RuntimeError(f"HTTP {result.status}")
    if result.headers.get("etag"):
        request_state["etag"] = result.headers["etag"]
    if result.headers.get("last-modified"):
        request_state["last_modified"] = result.headers["last-modified"]
    content_type = result.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    if adapter in {"rss", "atom", "feed"}:
        items = parse_feed(result.body, source, options, since)
    else:
        try:
            payload = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("machine endpoint returned invalid JSON") from exc
        if adapter == "federal-register":
            items = parse_federal_register(payload, source, options, since)
        elif adapter == "sec-submissions":
            items = parse_sec_submissions(payload, source, options, since)
        else:
            items = parse_sec_companyfacts(payload, source, options, since)
    for item in items:
        item.http_status = result.status
        item.content_type = content_type
    return items, "ok"


def _collection(path: Path, key: str, now: dt.datetime) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.exists():
        payload = {"schema_version": "1.0.0", "updated_at": iso_datetime(now), key: []}
        return payload, payload[key]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ValueError(f"{path} must contain an object envelope with '{key}'")
    records = [dict(item) for item in payload[key] if isinstance(item, Mapping)]
    return payload, records


def _record_keys(record: Mapping[str, Any], kind: str) -> set[str]:
    keys = {f"id:{record.get('id')}"} if record.get("id") else set()
    if kind == "events":
        url = canonicalize_url(record.get("primary_url"))
        date = clean_text(record.get("event_date"))
        title = title_key(record.get("title"))
        if title and date:
            keys.add(f"title-date:{title}|{date}")
    else:
        url = canonicalize_url(record.get("discovery_url"))
        title = title_key(record.get("title"))
        date = clean_text(record.get("event_date"))
        if title and date:
            keys.add(f"title-date:{title}|{date}")
    if url:
        keys.add(f"url:{url}")
    return keys


def merge_records(
    existing: Sequence[Mapping[str, Any]],
    incoming: Sequence[Mapping[str, Any]],
    kind: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for raw in [*existing, *incoming]:
        record = copy.deepcopy(dict(raw))
        matches = {index[key] for key in _record_keys(record, kind) if key in index}
        if matches:
            continue  # Existing/first-seen record wins; stable history is not rewritten.
        url_field = "primary_url" if kind == "events" else "discovery_url"
        canonical = canonicalize_url(record.get(url_field))
        if canonical:
            record[url_field] = canonical
        record["content_hash"] = content_hash(record)
        output.append(record)
        position = len(output) - 1
        for key in _record_keys(record, kind):
            index[key] = position
    return sorted(
        output,
        key=lambda item: (
            clean_text(item.get("event_date") or item.get("discovered_at")),
            clean_text(item.get("id")),
        ),
        reverse=True,
    )


def remove_published_candidates(
    candidates: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    event_ids = {clean_text(event.get("id")) for event in events}
    event_urls = {canonicalize_url(event.get("primary_url")) for event in events}
    event_title_dates = {
        (title_key(event.get("title")), clean_text(event.get("event_date")))
        for event in events
    }
    retained = []
    for raw in candidates:
        candidate = dict(raw)
        if (
            clean_text(candidate.get("id")) in event_ids
            or canonicalize_url(candidate.get("discovery_url")) in event_urls
            or (
                title_key(candidate.get("title")),
                clean_text(candidate.get("event_date")),
            )
            in event_title_dates
        ):
            continue
        candidate["content_hash"] = content_hash(candidate)
        retained.append(candidate)
    return retained


def _write_json(path: Path, payload: Any) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)
    return True


@dataclasses.dataclass
class CrawlSummary:
    sources_total: int = 0
    sources_succeeded: int = 0
    sources_skipped: int = 0
    sources_failed: int = 0
    events_added: int = 0
    candidates_added: int = 0


def run_pipeline(
    config_path: Path = ROOT / "config" / "sources.json",
    events_path: Path = ROOT / "data" / "events.json",
    candidates_path: Path = ROOT / "data" / "candidates.json",
    state_path: Path = ROOT / "data" / ".crawl-state.json",
    *,
    now: dt.datetime | None = None,
    overlap_hours: int = 72,
    client: HttpClient | None = None,
    selected_sources: set[str] | None = None,
    write: bool = True,
) -> CrawlSummary:
    now = (now or utcnow()).astimezone(dt.timezone.utc)
    since = now - dt.timedelta(hours=max(1, overlap_hours))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    sources = config.get("sources") if isinstance(config, Mapping) else None
    if not isinstance(sources, list):
        raise ValueError("config/sources.json must contain a sources array")
    event_envelope, existing_events = _collection(events_path, "events", now)
    candidate_envelope, existing_candidates = _collection(candidates_path, "candidates", now)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    else:
        state = {}
    state.setdefault("version", 1)
    source_states = state.setdefault("sources", {})
    if not isinstance(source_states, dict):
        source_states = {}
        state["sources"] = source_states
    http = client or HttpClient(
        user_agent=os.environ.get("AI_FINANCE_RADAR_USER_AGENT", USER_AGENT)
    )
    incoming_events = []
    incoming_candidates = []
    summary = CrawlSummary()
    for source in sources:
        if not isinstance(source, Mapping):
            summary.sources_failed += 1
            continue
        source_id = clean_text(source.get("id"))
        if selected_sources and source_id not in selected_sources:
            continue
        summary.sources_total += 1
        if source.get("enabled") is False:
            summary.sources_skipped += 1
            continue
        if isinstance(http, FixtureHttpClient) and not source.get("fixture"):
            summary.sources_skipped += 1
            continue
        source_state = source_states.setdefault(source_id, {})
        if not isinstance(source_state, dict):
            source_state = {}
            source_states[source_id] = source_state
        source_state["last_attempt_at"] = iso_datetime(now)
        try:
            items, status = crawl_source(source, http, source_state, since, now)
            source_state["last_status"] = status
            if status.startswith("skipped-"):
                summary.sources_skipped += 1
                continue
            summary.sources_succeeded += 1
            source_state.pop("last_error", None)
            for item in items:
                normalized = normalize_item(item, source, now)
                if normalized is None:
                    continue
                destination, record = normalized
                (incoming_events if destination == "event" else incoming_candidates).append(record)
        except Exception as exc:  # Deliberately isolate every configured source.
            summary.sources_failed += 1
            source_state["last_status"] = "failed"
            source_state["last_error"] = f"{type(exc).__name__}: {exc}"
            LOG.warning("%s failed non-fatally: %s", source_id, exc)
    merged_events = merge_records(existing_events, incoming_events, "events")
    merged_candidates = merge_records(existing_candidates, incoming_candidates, "candidates")
    merged_candidates = remove_published_candidates(merged_candidates, merged_events)
    summary.events_added = len(merged_events) - len(existing_events)
    summary.candidates_added = len(merged_candidates) - len(existing_candidates)
    if write:
        if merged_events != existing_events:
            event_envelope["updated_at"] = iso_datetime(now)
            event_envelope["events"] = merged_events
            _write_json(events_path, event_envelope)
        if merged_candidates != existing_candidates:
            candidate_envelope["updated_at"] = iso_datetime(now)
            candidate_envelope["candidates"] = merged_candidates
            _write_json(candidates_path, candidate_envelope)
        state["last_run_at"] = iso_datetime(now)
        state["overlap_hours"] = max(1, overlap_hours)
        _write_json(state_path, state)
    return summary


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/sources.json")
    parser.add_argument("--events", default="data/events.json")
    parser.add_argument("--candidates", default="data/candidates.json")
    parser.add_argument("--state", default="data/.crawl-state.json")
    parser.add_argument("--overlap-hours", type=int, default=72)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument(
        "--offline",
        nargs="?",
        const="tests/fixtures",
        metavar="FIXTURE_DIR",
        help="use deterministic local fixtures (default: tests/fixtures)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        offline_client = (
            FixtureHttpClient(_path(args.offline))
            if args.offline is not None
            else None
        )
        offline_now = None
        overlap_hours = args.overlap_hours
        if offline_client is not None:
            config_payload = json.loads(_path(args.config).read_text(encoding="utf-8"))
            offline_now = parse_datetime(config_payload.get("offline_retrieved_at"))
            if offline_now is None:
                raise ValueError("offline_retrieved_at is missing or invalid")
            overlap_hours = max(overlap_hours, 24 * 365 * 20)
        summary = run_pipeline(
            _path(args.config),
            _path(args.events),
            _path(args.candidates),
            _path(args.state),
            now=offline_now,
            overlap_hours=overlap_hours,
            client=offline_client,
            selected_sources=set(args.source) or None,
            write=not args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("pipeline setup failed: %s", exc)
        return 2
    print(json.dumps(dataclasses.asdict(summary), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
