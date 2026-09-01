#!/usr/bin/env python3
"""Build the deterministic static AI × Finance Radar site using stdlib only."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
import sys
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urljoin, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE_URL = "https://yzc-666.github.io/ai-finance-radar/"
ROOT_PAGES = ("index.html", "companies.html", "methodology.html", "404.html")
ASSETS = (
    "assets/css/style.css",
    "assets/css/styles.css",
    "assets/js/app.js",
    "assets/icons/favicon.svg",
    "assets/icons/social-card.svg",
)
PLACEHOLDERS = ("robots.txt", "sitemap.xml", "feed.xml")
DATASETS = ("companies.json", "events.json")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
COUNTRIES = {"CN", "US"}
SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ATOM_NS = "http://www.w3.org/2005/Atom"


class BuildError(ValueError):
    """Raised when source data cannot safely produce a public build."""


def txt(value: Any) -> str:
    return "" if value is None else str(value)


def esc(value: Any) -> str:
    return html.escape(txt(value), quote=True)


def token_label(value: Any) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[_-]+", txt(value)) if part)


def slugify(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", txt(value).lower()).strip("-")
    return slug or "record"


def country_code(value: Any) -> str:
    normalized = txt(value).strip().lower()
    if normalized in {"cn", "china", "people's republic of china"}:
        return "CN"
    if normalized in {"us", "usa", "united states", "united states of america"}:
        return "US"
    return txt(value).upper()


def country_name(value: Any) -> str:
    return {"CN": "China", "US": "United States"}.get(country_code(value), txt(value))


def tier_label(value: Any) -> str:
    raw = txt(value).strip()
    match = re.search(r"(?:tier[\s_-]*)?([123])$", raw, flags=re.IGNORECASE)
    if match:
        return f"Tier {match.group(1)}"
    if raw.lower() == "primary":
        return "Tier 1"
    if raw.lower() == "secondary":
        return "Tier 2"
    return token_label(raw) or "Source tier unavailable"


def parse_iso(value: Any, location: str) -> datetime:
    raw = txt(value).strip()
    if not raw:
        raise BuildError(f"{location} must be a non-empty ISO date or timestamp")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(raw), time.min)
        except ValueError as error:
            raise BuildError(f"{location} must be an ISO 8601 date or timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def human_date(value: Any) -> str:
    parsed = parse_iso(value, "date")
    return f"{parsed.strftime('%d').lstrip('0')} {parsed.strftime('%b %Y')}"


def human_datetime(value: Any) -> str:
    raw = txt(value)
    parsed = parse_iso(raw, "timestamp")
    if "T" not in raw:
        return human_date(raw)
    return f"{parsed.strftime('%d').lstrip('0')} {parsed.strftime('%b %Y, %H:%M UTC')}"


def is_url(value: Any) -> bool:
    try:
        parsed = urlsplit(txt(value))
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def latest(values: Sequence[Any]) -> str:
    present = [txt(value) for value in values if txt(value)]
    if not present:
        return ""
    return max(present, key=lambda value: parse_iso(value, "timestamp"))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BuildError(f"Required input is missing: {path.relative_to(ROOT)}") from error
    except json.JSONDecodeError as error:
        raise BuildError(
            f"{path.relative_to(ROOT)} is invalid JSON at line {error.lineno}, column {error.colno}"
        ) from error


def extract(payload: Any, key: str, source: str) -> tuple[str, list[Mapping[str, Any]]]:
    if isinstance(payload, list):
        records = payload
        updated_at = latest(
            [
                item.get("retrieved_at") or item.get("published_at") or item.get("last_verified_at")
                for item in records
                if isinstance(item, dict)
            ]
        )
    elif isinstance(payload, dict) and isinstance(payload.get(key), list):
        records = payload[key]
        updated_at = txt(payload.get("updated_at") or payload.get("generated_at"))
    else:
        raise BuildError(f"{source} must be an array or an envelope containing {key}[]")
    if not updated_at:
        raise BuildError(f"{source} must provide or contain a derivable update timestamp")
    parse_iso(updated_at, f"{source}.updated_at")
    if any(not isinstance(record, dict) for record in records):
        raise BuildError(f"{source}.{key} must contain only objects")
    return updated_at, records


def normalize_company(raw: Mapping[str, Any], updated_at: str) -> dict[str, Any]:
    homepage = txt(raw.get("homepage") or raw.get("official_homepage"))
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raw_sources = raw.get("provenance")
    if not isinstance(raw_sources, list) or not raw_sources:
        raw_sources = [
            {"url": url, "publisher": raw.get("name"), "tier": "primary"}
            for url in raw.get("source_urls", [])
        ]
    products = []
    for product in raw.get("products", []):
        if not isinstance(product, dict):
            products.append(product)
            continue
        products.append(
            {
                **product,
                "note": txt(
                    product.get("note") or product.get("description") or product.get("category")
                ),
                "url": txt(product.get("url") or homepage),
            }
        )
    verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
    return {
        **raw,
        "country": country_code(raw.get("country") or next(iter(raw.get("jurisdictions", [])), "")),
        "homepage": homepage,
        "last_verified_at": txt(
            raw.get("last_verified_at") or verification.get("verified_at") or updated_at
        ),
        "one_liner": txt(raw.get("one_liner") or raw.get("description")),
        "products": products,
        "sectors": raw.get("sectors", []),
        "slug": txt(raw.get("slug") or slugify(raw.get("name") or raw.get("id"))),
        "sources": [
            {
                **source,
                "publisher": txt(source.get("publisher") or raw.get("name") or "Official source"),
                "tier": source.get("tier", source.get("source_tier", "primary")),
            }
            if isinstance(source, dict)
            else source
            for source in raw_sources
        ],
        "verification_status": txt(
            raw.get("verification_status") or verification.get("status") or "verified"
        ),
    }


def normalize_event(raw: Mapping[str, Any], updated_at: str) -> dict[str, Any]:
    primary = raw.get("primary_source") if isinstance(raw.get("primary_source"), dict) else {}
    verification = raw.get("verification") if isinstance(raw.get("verification"), dict) else {}
    retrieval = raw.get("retrieval") if isinstance(raw.get("retrieval"), dict) else {}
    fallback = re.sub(r"^evt-\d{4}-\d{2}-\d{2}-", "", txt(raw.get("slug") or raw.get("id")))
    title = txt(raw.get("title") or primary.get("title") or token_label(fallback))
    status = txt(raw.get("verification_status"))
    if not status and (raw.get("status") == "published" or verification):
        status = "verified"
    return {
        **raw,
        "company_ids": raw.get("company_ids", []),
        "content_hash": txt(raw.get("content_hash") or raw.get("sha256")),
        "country": country_code(raw.get("country") or next(iter(raw.get("jurisdictions", [])), "")),
        "published_at": txt(
            raw.get("published_at") or primary.get("published_on") or raw.get("event_date")
        ),
        "publisher": txt(raw.get("publisher") or primary.get("publisher") or "Official source"),
        "primary_url": txt(raw.get("primary_url") or primary.get("url")),
        "retrieved_at": txt(raw.get("retrieved_at") or retrieval.get("retrieved_at") or updated_at),
        "sectors": raw.get("sectors", []),
        "slug": txt(raw.get("slug") or slugify(title or raw.get("id"))),
        "source_tier": raw.get("source_tier", primary.get("source_tier", "primary")),
        "summary": txt(raw.get("summary")),
        "title": title,
        "type": txt(raw.get("type") or raw.get("event_type") or "event"),
        "verification_status": status or "unverified",
    }


def required_string(record: Mapping[str, Any], key: str, location: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{location}.{key} must be a non-empty string")
    return value


def string_list(record: Mapping[str, Any], key: str, location: str) -> list[str]:
    values = record.get(key)
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        raise BuildError(f"{location}.{key} must be an array of non-empty strings")
    if len(values) != len(set(values)):
        raise BuildError(f"{location}.{key} must not contain duplicates")
    return values


def validate_companies(companies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    slugs: set[str] = set()
    for index, company in enumerate(companies):
        location = f"companies[{index}]"
        for key in (
            "id", "slug", "name", "country", "homepage", "one_liner",
            "verification_status", "last_verified_at",
        ):
            required_string(company, key, location)
        if company["country"] not in COUNTRIES:
            raise BuildError(f"{location}.country must be CN or US")
        if not SLUG_RE.fullmatch(company["slug"]):
            raise BuildError(f"{location}.slug must use lowercase kebab-case")
        if not is_url(company["homepage"]):
            raise BuildError(f"{location}.homepage must be an absolute HTTP(S) URL")
        parse_iso(company["last_verified_at"], f"{location}.last_verified_at")
        string_list(company, "sectors", location)
        if company["id"] in by_id or company["slug"] in slugs:
            raise BuildError(f"{location} duplicates a company id or slug")
        by_id[company["id"]] = company
        slugs.add(company["slug"])
        if not isinstance(company.get("products"), list):
            raise BuildError(f"{location}.products must be an array")
        for product_index, product in enumerate(company["products"]):
            product_location = f"{location}.products[{product_index}]"
            if not isinstance(product, dict):
                raise BuildError(f"{product_location} must be an object")
            required_string(product, "name", product_location)
            if not is_url(product.get("url")):
                raise BuildError(f"{product_location}.url must be an absolute HTTP(S) URL")
            if not isinstance(product.get("note"), str):
                raise BuildError(f"{product_location}.note must be a string")
        if not isinstance(company.get("sources"), list) or not company["sources"]:
            raise BuildError(f"{location}.sources must contain at least one source")
        for source_index, source in enumerate(company["sources"]):
            source_location = f"{location}.sources[{source_index}]"
            if not isinstance(source, dict):
                raise BuildError(f"{source_location} must be an object")
            required_string(source, "publisher", source_location)
            if not is_url(source.get("url")):
                raise BuildError(f"{source_location}.url must be an absolute HTTP(S) URL")
            if isinstance(source.get("tier"), bool) or not isinstance(source.get("tier"), (str, int)):
                raise BuildError(f"{source_location}.tier must be a string or integer")
    return by_id


def validate_events(events: list[dict[str, Any]], company_ids: set[str]) -> None:
    ids: set[str] = set()
    slugs: set[str] = set()
    for index, event in enumerate(events):
        location = f"events[{index}]"
        for key in (
            "id", "slug", "type", "title", "country", "event_date", "published_at",
            "summary", "primary_url", "publisher", "retrieved_at",
            "verification_status", "content_hash",
        ):
            required_string(event, key, location)
        if event["country"] not in COUNTRIES:
            raise BuildError(f"{location}.country must be CN or US")
        if not SLUG_RE.fullmatch(event["slug"]):
            raise BuildError(f"{location}.slug must use lowercase kebab-case")
        if not is_url(event["primary_url"]):
            raise BuildError(f"{location}.primary_url must be an absolute HTTP(S) URL")
        for key in ("event_date", "published_at", "retrieved_at"):
            parse_iso(event[key], f"{location}.{key}")
        referenced = string_list(event, "company_ids", location)
        unknown = sorted(set(referenced) - company_ids)
        if unknown:
            raise BuildError(f"{location}.company_ids contains unknown ids: {', '.join(unknown)}")
        string_list(event, "sectors", location)
        if event["id"] in ids or event["slug"] in slugs:
            raise BuildError(f"{location} duplicates an event id or slug")
        ids.add(event["id"])
        slugs.add(event["slug"])
        if isinstance(event.get("source_tier"), bool) or not isinstance(
            event.get("source_tier"), (str, int)
        ):
            raise BuildError(f"{location}.source_tier must be a string or integer")
        if event.get("context") is not None and not isinstance(event.get("context"), str):
            raise BuildError(f"{location}.context must be a string")


def is_verified(record: Mapping[str, Any]) -> bool:
    return txt(record.get("verification_status")).lower() in {
        "verified", "published", "primary-source",
    }


def site_url(base: str, path: str = "") -> str:
    return urljoin(base, path)


def head(title: str, description: str, canonical: str, base: str, schema: Mapping[str, Any]) -> str:
    image = site_url(base, "assets/icons/social-card.svg")
    json_ld = json.dumps(schema, ensure_ascii=False, separators=(",", ":"), sort_keys=True).replace(
        "</", "<\\/"
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="dark">
    <meta name="theme-color" content="#07111f">
    <meta name="description" content="{esc(description)}">
    <meta name="robots" content="index,follow">
    <link rel="canonical" href="{esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:site_name" content="AI × Finance Radar">
    <meta property="og:title" content="{esc(title)}">
    <meta property="og:description" content="{esc(description)}">
    <meta property="og:url" content="{esc(canonical)}">
    <meta property="og:image" content="{esc(image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{esc(title)}">
    <meta name="twitter:description" content="{esc(description)}">
    <meta name="twitter:image" content="{esc(image)}">
    <title>{esc(title)}</title>
    <link rel="icon" href="../assets/icons/favicon.svg" type="image/svg+xml">
    <link rel="alternate" type="application/rss+xml" title="AI × Finance Radar" href="../feed.xml">
    <link rel="stylesheet" href="../assets/css/styles.css">
    <script type="application/ld+json">{json_ld}</script>
    <script defer src="../assets/js/app.js" data-radar-app></script>
  </head>"""


def header(active: str) -> str:
    links = []
    for key, path, label in (
        ("events", "../index.html", "Latest"),
        ("companies", "../companies.html", "Companies"),
        ("methodology", "../methodology.html", "Methodology"),
    ):
        current = ' aria-current="page"' if key == active else ""
        links.append(f'<a href="{path}"{current}>{label}</a>')
    return f"""  <body data-page="detail">
    <a class="skip-link" href="#main-content">Skip to content</a>
    <header class="site-header"><div class="shell header-shell">
      <a class="brand" href="../index.html" aria-label="AI × Finance Radar home"><span class="brand-mark" aria-hidden="true">A×F</span><span class="brand-name">AI × Finance <strong>Radar</strong></span></a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="primary-navigation" data-nav-toggle><span class="sr-only">Toggle navigation</span><span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span></button>
      <nav class="primary-nav" id="primary-navigation" aria-label="Primary navigation" data-nav>{"".join(links)}<a class="nav-data-link" href="../data/events.json">JSON <span aria-hidden="true">↗</span></a></nav>
    </div></header>"""


def footer(updated_at: str) -> str:
    return f"""    <footer class="site-footer"><div class="shell footer-grid">
      <div><a class="brand footer-brand" href="../index.html">AI × Finance <strong>Radar</strong></a><p>Independent, source-linked research on AI in financial services.</p></div>
      <nav aria-label="Footer navigation"><a href="../index.html">Latest</a><a href="../companies.html">Companies</a><a href="../methodology.html">Methodology</a><a href="../feed.xml">RSS</a></nav>
      <p class="footer-meta">Last dataset update: {esc(human_datetime(updated_at))}<br>Not investment advice.</p>
    </div></footer>
  </body>
</html>
"""


def badge(status: Any) -> str:
    css = "badge badge-verified" if is_verified({"verification_status": status}) else "badge"
    return f'<span class="{css}">{esc(token_label(status))}</span>'


def chips(sectors: Sequence[Any], destination: str) -> str:
    return "".join(
        f'<a class="chip" href="{destination}?sector={quote(txt(sector), safe="")}">{esc(sector)}</a>'
        for sector in sectors
    )


def render_company(
    company: Mapping[str, Any],
    related: Sequence[Mapping[str, Any]],
    base: str,
    updated_at: str,
) -> str:
    canonical = site_url(base, f"companies/{quote(company['slug'])}.html")
    title = f"{company['name']} — AI × Finance Radar"
    description = txt(company["one_liner"])[:190]
    products = "".join(
        f'<li class="product-record"><div><h3>{esc(item["name"])}</h3><p>{esc(item["note"])}</p></div><a class="button button-secondary" href="{esc(item["url"])}" target="_blank" rel="noopener noreferrer">Official product <span aria-hidden="true">↗</span></a></li>'
        for item in company["products"]
    )
    sources = "".join(
        f'<li class="evidence-item"><div><h3>{esc(item["publisher"])}</h3><p>{esc(tier_label(item["tier"]))} company evidence</p></div><a class="button button-secondary" href="{esc(item["url"])}" target="_blank" rel="noopener noreferrer">Open source <span aria-hidden="true">↗</span></a></li>'
        for item in company["sources"]
    )
    related_items = "".join(
        f'<li class="related-record"><time datetime="{esc(item["event_date"])}">{esc(human_date(item["event_date"]))}</time><div><h3><a href="../events/{quote(item["slug"])}.html">{esc(item["title"])}</a></h3><p>{esc(item["summary"])}</p></div></li>'
        for item in related
    )
    related_section = (
        f'<section class="detail-section"><p class="eyebrow">Verified chronology</p><h2>Related events</h2><ul class="related-records">{related_items}</ul></section>'
        if related_items else ""
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "description": company["one_liner"],
        "name": company["name"],
        "url": company["homepage"],
    }
    body = f"""
    <main class="detail-main shell" id="main-content">
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="../index.html">Radar</a><span aria-hidden="true">/</span><a href="../companies.html">Companies</a><span aria-hidden="true">/</span><span aria-current="page">{esc(company["name"])}</span></nav>
      <header class="detail-hero"><p class="eyebrow">Company evidence profile · {esc(country_name(company["country"]))}</p><h1>{esc(company["name"])}</h1><p class="detail-deck">{esc(company["one_liner"])}</p><div class="detail-meta">{badge(company["verification_status"])}<span class="badge badge-country">{esc(company["country"])}</span>{chips(company["sectors"], "../companies.html")}</div></header>
      <div class="detail-grid">
        <div class="detail-content">
          <section class="detail-section"><p class="eyebrow">First-party identity</p><h2>Official homepage</h2><div class="primary-evidence"><h3>{esc(company["name"])}</h3><p>Use the organization’s own site for current product and company information.</p><a class="button button-primary" href="{esc(company["homepage"])}" target="_blank" rel="noopener noreferrer">Visit official homepage <span aria-hidden="true">↗</span></a></div></section>
          {f'<section class="detail-section"><p class="eyebrow">Official destinations</p><h2>Products</h2><ul class="product-records">{products}</ul></section>' if products else ""}
          <section class="detail-section"><p class="eyebrow">Source record</p><h2>Company evidence</h2><ul class="evidence-list">{sources}</ul></section>
          {related_section}
        </div>
        <aside class="detail-sidebar" aria-label="Record details">
          <section class="sidebar-card"><p class="card-kicker">Record details</p><dl class="record-table"><div><dt>ID</dt><dd>{esc(company["id"])}</dd></div><div><dt>Country</dt><dd>{esc(country_name(company["country"]))} ({esc(company["country"])})</dd></div><div><dt>Products</dt><dd>{len(company["products"])}</dd></div><div><dt>Sources</dt><dd>{len(company["sources"])}</dd></div><div><dt>Verified</dt><dd>{esc(human_datetime(company["last_verified_at"]))}</dd></div></dl></section>
          <section class="sidebar-card"><h2>Continue exploring</h2><div class="sidebar-links"><a href="../companies.html#company-{esc(company["slug"])}">Back to directory →</a><a href="../index.html">Latest verified events →</a><a href="../methodology.html">Read the methodology →</a></div></section>
        </aside>
      </div>
    </main>
"""
    return head(title, description, canonical, base, schema) + "\n" + header("companies") + body + footer(updated_at)


def render_event(
    event: Mapping[str, Any],
    companies: Mapping[str, Mapping[str, Any]],
    base: str,
    updated_at: str,
) -> str:
    canonical = site_url(base, f"events/{quote(event['slug'])}.html")
    title = f"{event['title']} — AI × Finance Radar"
    linked = [companies[item] for item in event["company_ids"] if item in companies]
    organizations = "".join(
        f'<li class="organization-record"><div><h3><a href="../companies/{quote(item["slug"])}.html">{esc(item["name"])}</a></h3><p>{esc(item["one_liner"])}</p></div><a class="button button-secondary" href="{esc(item["homepage"])}" target="_blank" rel="noopener noreferrer">Official site <span aria-hidden="true">↗</span></a></li>'
        for item in linked
    )
    organization_section = (
        f'<section class="detail-section"><p class="eyebrow">Linked organizations</p><h2>Companies in this record</h2><ul class="organization-records">{organizations}</ul></section>'
        if organizations else ""
    )
    context_section = (
        f'<section class="detail-section"><p class="eyebrow">Context</p><h2>Why this record matters</h2><div class="context-block"><p>{esc(event["context"])}</p></div></section>'
        if txt(event.get("context")).strip() else ""
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "datePublished": event["published_at"],
        "description": event["summary"],
        "headline": event["title"],
        "isBasedOn": event["primary_url"],
        "mainEntityOfPage": canonical,
    }
    body = f"""
    <main class="detail-main shell" id="main-content">
      <nav class="breadcrumb" aria-label="Breadcrumb"><a href="../index.html">Radar</a><span aria-hidden="true">/</span><a href="../index.html#latest-events">Events</a><span aria-hidden="true">/</span><span aria-current="page">{esc(event["title"])}</span></nav>
      <header class="detail-hero"><p class="eyebrow">{esc(token_label(event["type"]))} · {esc(country_name(event["country"]))}</p><h1>{esc(event["title"])}</h1><p class="detail-deck">{esc(event["summary"])}</p><div class="detail-meta">{badge(event["verification_status"])}<span class="badge badge-country">{esc(event["country"])}</span><time class="badge" datetime="{esc(event["event_date"])}">{esc(human_date(event["event_date"]))}</time>{chips(event["sectors"], "../index.html")}</div></header>
      <div class="detail-grid">
        <div class="detail-content">
          <section class="detail-section"><p class="eyebrow">Primary evidence</p><h2>Source of record</h2><div class="primary-evidence"><h3>{esc(event["publisher"])}</h3><p>{esc(tier_label(event["source_tier"]))} source · Published {esc(human_datetime(event["published_at"]))} · Retrieved {esc(human_datetime(event["retrieved_at"]))}</p><a class="button button-primary" href="{esc(event["primary_url"])}" target="_blank" rel="noopener noreferrer">Open primary source <span aria-hidden="true">↗</span></a></div></section>
          {context_section}{organization_section}
        </div>
        <aside class="detail-sidebar" aria-label="Record details">
          <section class="sidebar-card"><p class="card-kicker">Provenance</p><dl class="record-table"><div><dt>Record ID</dt><dd>{esc(event["id"])}</dd></div><div><dt>Type</dt><dd>{esc(token_label(event["type"]))}</dd></div><div><dt>Event date</dt><dd>{esc(event["event_date"])}</dd></div><div><dt>Published</dt><dd>{esc(event["published_at"])}</dd></div><div><dt>Retrieved</dt><dd>{esc(event["retrieved_at"])}</dd></div><div><dt>Source tier</dt><dd>{esc(tier_label(event["source_tier"]))}</dd></div><div><dt>Content hash</dt><dd>{esc(event["content_hash"])}</dd></div></dl></section>
          <section class="sidebar-card"><h2>Continue exploring</h2><div class="sidebar-links"><a href="../index.html#event-{esc(event["slug"])}">Back to this feed record →</a><a href="../companies.html">Browse companies →</a><a href="../methodology.html">Read the methodology →</a></div></section>
        </aside>
      </div>
    </main>
"""
    return head(title, txt(event["summary"])[:190], canonical, base, schema) + "\n" + header("events") + body + footer(updated_at)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def copy_text(source: Path, destination: Path, base: str) -> None:
    content = source.read_text(encoding="utf-8")
    if base != DEFAULT_SITE_URL:
        content = content.replace(DEFAULT_SITE_URL, base)
    write_text(destination, content)


def nested(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def write_csvs(output: Path, companies: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]) -> None:
    directory = output / "data" / "exports"
    directory.mkdir(parents=True, exist_ok=True)
    company_fields = (
        "id", "slug", "name", "country", "homepage", "one_liner", "sectors",
        "products", "sources", "verification_status", "last_verified_at",
    )
    event_fields = (
        "id", "slug", "type", "title", "company_ids", "country", "sectors",
        "event_date", "published_at", "summary", "context", "primary_url", "publisher",
        "source_tier", "retrieved_at", "verification_status", "content_hash",
    )
    with (directory / "companies.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, company_fields, lineterminator="\n")
        writer.writeheader()
        for company in sorted(companies, key=lambda item: item["slug"]):
            row = dict(company)
            row.update(
                sectors="|".join(company["sectors"]),
                products=nested(company["products"]),
                sources=nested(company["sources"]),
            )
            writer.writerow({field: row.get(field, "") for field in company_fields})
    with (directory / "events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, event_fields, lineterminator="\n")
        writer.writeheader()
        for event in sorted(events, key=lambda item: item["slug"]):
            row = dict(event)
            row.update(company_ids="|".join(event["company_ids"]), sectors="|".join(event["sectors"]))
            writer.writerow({field: row.get(field, "") for field in event_fields})


def write_feed(output: Path, events: Sequence[Mapping[str, Any]], base: str, updated_at: str) -> None:
    ET.register_namespace("atom", ATOM_NS)
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    for name, value in (
        ("title", "AI × Finance Radar"),
        ("link", base),
        ("description", "Verified, source-linked developments in AI and financial services."),
        ("language", "en"),
        ("lastBuildDate", format_datetime(parse_iso(updated_at, "updated_at"), usegmt=True)),
    ):
        ET.SubElement(channel, name).text = value
    ET.SubElement(
        channel,
        f"{{{ATOM_NS}}}link",
        {"href": site_url(base, "feed.xml"), "rel": "self", "type": "application/rss+xml"},
    )
    ordered = sorted(
        events,
        key=lambda item: (parse_iso(item["event_date"], "event_date"), item["slug"]),
        reverse=True,
    )
    for event in ordered:
        item = ET.SubElement(channel, "item")
        link = site_url(base, f"events/{quote(event['slug'])}.html")
        ET.SubElement(item, "title").text = event["title"]
        ET.SubElement(item, "link").text = link
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = link
        ET.SubElement(item, "pubDate").text = format_datetime(
            parse_iso(event["published_at"], "published_at"), usegmt=True
        )
        ET.SubElement(item, "description").text = event["summary"]
        ET.SubElement(item, "source", {"url": event["primary_url"]}).text = event["publisher"]
        ET.SubElement(item, "category").text = token_label(event["type"])
        for sector in event["sectors"]:
            ET.SubElement(item, "category").text = sector
    ET.indent(rss, space="  ")
    ET.ElementTree(rss).write(
        output / "feed.xml", encoding="utf-8", xml_declaration=True, short_empty_elements=False
    )


def sitemap_entry(root: ET.Element, base: str, path: str, modified: str = "") -> None:
    entry = ET.SubElement(root, f"{{{SITEMAP_NS}}}url")
    ET.SubElement(entry, f"{{{SITEMAP_NS}}}loc").text = site_url(base, path)
    if modified:
        ET.SubElement(entry, f"{{{SITEMAP_NS}}}lastmod").text = modified


def write_sitemap(
    output: Path,
    companies: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    base: str,
    company_updated: str,
    event_updated: str,
) -> None:
    ET.register_namespace("", SITEMAP_NS)
    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    sitemap_entry(root, base, "", event_updated)
    sitemap_entry(root, base, "companies.html", company_updated)
    sitemap_entry(root, base, "methodology.html")
    for company in sorted(companies, key=lambda item: item["slug"]):
        sitemap_entry(
            root, base, f"companies/{quote(company['slug'])}.html", company["last_verified_at"]
        )
    for event in sorted(events, key=lambda item: item["slug"]):
        sitemap_entry(root, base, f"events/{quote(event['slug'])}.html", event["published_at"])
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(
        output / "sitemap.xml", encoding="utf-8", xml_declaration=True, short_empty_elements=False
    )


def validate_sources() -> None:
    expected = [ROOT / item for item in (*ROOT_PAGES, *ASSETS, *PLACEHOLDERS)]
    expected.extend(ROOT / "data" / item for item in DATASETS)
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.is_file()]
    if missing:
        raise BuildError("Missing required source files:\n" + "\n".join(f"  - {item}" for item in missing))


def normalize_base(value: str) -> str:
    if not is_url(value):
        raise BuildError("--site-url must be an absolute HTTP(S) URL")
    return value if value.endswith("/") else value + "/"


def prepare_output(output: Path) -> Path:
    resolved = output.resolve()
    if resolved == ROOT or resolved in ROOT.parents:
        raise BuildError("Refusing to use the repository or one of its parents as output")
    if resolved.exists():
        if not resolved.is_dir():
            raise BuildError(f"Output exists and is not a directory: {resolved}")
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True)
    return resolved


def load_and_validate() -> tuple[str, list[dict[str, Any]], str, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    validate_sources()
    company_updated, raw_companies = extract(
        load_json(ROOT / "data" / "companies.json"), "companies", "data/companies.json"
    )
    event_updated, raw_events = extract(
        load_json(ROOT / "data" / "events.json"), "events", "data/events.json"
    )
    companies = [normalize_company(item, company_updated) for item in raw_companies]
    events = [normalize_event(item, event_updated) for item in raw_events]
    companies_by_id = validate_companies(companies)
    validate_events(events, set(companies_by_id))
    return company_updated, companies, event_updated, events, companies_by_id


def build(output: Path, base: str, check_only: bool = False) -> tuple[int, int]:
    company_updated, companies, event_updated, events, companies_by_id = load_and_validate()
    published = [event for event in events if is_verified(event)]
    if check_only:
        return len(companies), len(published)
    output = prepare_output(output)
    for relative in (*ROOT_PAGES, *ASSETS):
        copy_text(ROOT / relative, output / relative, base)
    for filename in DATASETS:
        destination = output / "data" / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "data" / filename, destination)
    write_text(output / ".nojekyll", "")
    write_text(
        output / "robots.txt",
        f"User-agent: *\nAllow: /\n\nSitemap: {site_url(base, 'sitemap.xml')}\n",
    )
    related: dict[str, list[dict[str, Any]]] = {key: [] for key in companies_by_id}
    for event in published:
        for company_id in event["company_ids"]:
            related[company_id].append(event)
    for records in related.values():
        records.sort(key=lambda item: (parse_iso(item["event_date"], "date"), item["slug"]), reverse=True)
    for company in sorted(companies, key=lambda item: item["slug"]):
        write_text(
            output / "companies" / f"{company['slug']}.html",
            render_company(company, related.get(company["id"], []), base, company_updated),
        )
    for event in sorted(published, key=lambda item: item["slug"]):
        write_text(
            output / "events" / f"{event['slug']}.html",
            render_event(event, companies_by_id, base, event_updated),
        )
    write_csvs(output, companies, published)
    write_feed(output, published, base, event_updated)
    write_sitemap(output, companies, published, base, company_updated, event_updated)
    return len(companies), len(published)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", "--output-dir", dest="output", type=Path, default=ROOT / "dist",
        help="Build destination (default: dist/)",
    )
    parser.add_argument(
        "--site-url", "--base-url", dest="site_url", default=DEFAULT_SITE_URL,
        help=f"Canonical public base URL (default: {DEFAULT_SITE_URL})",
    )
    parser.add_argument(
        "--check", "--check-only", dest="check_only", action="store_true",
        help="Validate inputs without writing output",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        base = normalize_base(args.site_url)
        company_count, event_count = build(args.output, base, args.check_only)
    except (BuildError, OSError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    action = "Validated" if args.check_only else "Built"
    suffix = "" if args.check_only else f" into {args.output.resolve()}"
    print(f"{action} {company_count} company pages and {event_count} verified event pages{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
