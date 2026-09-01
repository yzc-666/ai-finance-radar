from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import crawl  # noqa: E402
import validate  # noqa: E402

NOW = crawl.parse_datetime("2026-09-01T16:00:00Z")
assert NOW is not None


def make_source(
    source_id: str,
    host: str,
    adapter: str,
    source_class: str = "government_primary",
    auto_publish: bool = True,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "name": source_id,
        "publisher": source_id,
        "owner": source_id,
        "source_tier": "primary" if auto_publish else "secondary",
        "publish_mode": "auto" if auto_publish else "candidate",
        "jurisdiction": ["US"],
        "jurisdictions": ["US"],
        "country": "US",
        "sectors": ["Financial Infrastructure"],
        "transport": {"protocol": "https", "formats": ["json", "xml"]},
        "canonical_url": f"https://{host}",
        "allowed_domains": [host],
        "company_ids": ["acme-ai"] if auto_publish else [],
        "source_class": source_class,
        "auto_publish": auto_publish,
        "allowed_fields": ["title", "date", "canonical_url"],
        "terms_license": {"redistribution": "metadata_only"},
        "rate_limit": {"requests_per_minute": 6000},
        "enabled": True,
        "machine_endpoint": {
            "adapter": adapter,
            "url": f"https://{host}/feed",
            "event_type": "product",
            "company_ids": ["acme-ai"] if auto_publish else [],
            "jurisdictions": ["US"],
            "sectors": ["Financial Infrastructure"],
            "delay_seconds": 0,
            "forms": ["8-K"],
        },
    }


def sources_payload() -> dict[str, Any]:
    official = make_source("official-feed", "alpha-sense.com", "rss")
    news = make_source(
        "news-feed", "techcrunch.com", "rss", "news_secondary", False
    )
    news["machine_endpoint"]["event_type"] = "funding"
    news["include_keywords"] = ["AI"]
    sec = make_source("sec-filings", "sec.gov", "sec-submissions")
    sec["machine_endpoint"].update(
        {
            "url": "https://data.sec.gov/submissions/CIK0000123456.json",
            "event_type": "regulation",
        }
    )
    return {
        "schema_version": "1.0.0",
        "updated_at": "2026-09-01T08:00:00Z",
        "offline_retrieved_at": "2026-09-01T08:00:00Z",
        "language": "en",
        "markets": ["CN", "US"],
        "taxonomy": {
            "sectors": list(crawl.SECTORS),
            "event_types": sorted(crawl.EVENT_TYPES),
        },
        "policy": {
            "auto_publish_tiers": ["primary"],
            "candidate_tiers": ["secondary"],
            "secondary_never_auto_publishes": True,
            "commercial_or_paywalled_scraping": False,
        },
        "official_domains": [
            {"domain": "alpha-sense.com", "publisher": "official-feed", "company_ids": ["acme-ai"]},
            {"domain": "sec.gov", "publisher": "sec-filings", "company_ids": []},
        ],
        "sources": [official, news, sec],
    }


def companies_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "updated_at": "2026-09-01T08:00:00Z",
        "companies": [
            {
                "id": "acme-ai",
                "slug": "acme-ai",
                "name": "Acme AI",
                "country": "US",
                "hq": "New York, NY",
                "founded_year": 2020,
                "homepage": "https://alpha-sense.com",
                "one_liner": "AI infrastructure for regulated financial operations.",
                "sectors": ["Financial Infrastructure"],
                "products": [
                    {
                        "id": "treasury-copilot",
                        "name": "Treasury Copilot",
                        "note": "AI-assisted treasury operations.",
                        "url": "https://alpha-sense.com/product",
                    }
                ],
                "sources": [{
                    "url": "https://alpha-sense.com",
                    "publisher": "Acme AI",
                    "tier": "primary",
                    "retrieved_at": "2026-09-01T08:00:00Z",
                    "note": "Official company website."
                }],
                "verification_status": "verified",
                "last_verified_at": "2026-09-01T08:00:00Z",
            }
        ],
    }


def raw_official() -> crawl.RawItem:
    configured = sources_payload()["sources"][0]
    records = crawl.parse_feed(
        (FIXTURES / "official_feed.xml").read_bytes(),
        configured,
        configured["machine_endpoint"],
        crawl.parse_datetime("2026-06-01T00:00:00Z"),
    )
    records[0].http_status = 200
    records[0].content_type = "application/rss+xml"
    return records[0]


def seeded_event() -> dict[str, Any]:
    destination, record = crawl.normalize_item(
        raw_official(), sources_payload()["sources"][0], NOW
    )
    assert destination == "event"
    return record


class MemoryClient:
    def __init__(self, bodies: Mapping[str, bytes], fail: set[str] | None = None):
        self.bodies = dict(bodies)
        self.fail = fail or set()

    def get(
        self,
        url: str,
        source: Mapping[str, Any],
        conditional: Mapping[str, Any] | None = None,
    ) -> crawl.HttpResult:
        source_id = str(source["id"])
        if source_id in self.fail:
            raise TimeoutError("fixture failure")
        body = self.bodies[source_id]
        content_type = "application/json" if body.lstrip().startswith(b"{") else "application/xml"
        return crawl.HttpResult(
            url, 200, {"content-type": content_type, "etag": '"fixture"'}, body
        )


def write_repo(root: Path) -> None:
    (root / "config").mkdir()
    (root / "data").mkdir()
    values = {
        "config/sources.json": sources_payload(),
        "data/companies.json": companies_payload(),
        "data/events.json": {
            "schema_version": "1.0.0",
            "updated_at": "2026-09-01T08:00:00Z",
            "events": [seeded_event()],
        },
        "data/candidates.json": {
            "schema_version": "1.0.0",
            "updated_at": "2026-09-01T08:00:00Z",
            "candidates": [],
        },
    }
    for name, value in values.items():
        (root / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class PipelineTests(unittest.TestCase):
    def test_atom_parser_and_deterministic_offline_normalization(self) -> None:
        configured = make_source("hebbia-feed", "hebbia.com", "atom")
        configured["machine_endpoint"]["jurisdictions"] = ["US"]
        configured["machine_endpoint"]["sectors"] = ["Research & Data"]
        records = crawl.parse_feed(
            (FIXTURES / "atom_feed.xml").read_bytes(),
            configured,
            configured["machine_endpoint"],
            crawl.dt.datetime(2000, 1, 1, tzinfo=crawl.dt.timezone.utc),
        )
        self.assertEqual(1, len(records))
        first = crawl.normalize_item(records[0], configured, NOW)
        second = crawl.normalize_item(records[0], configured, NOW)
        self.assertEqual(first, second)

    def test_cli_offline_fixture_mode(self) -> None:
        self.assertEqual(
            0,
            crawl.main(["--offline", str(FIXTURES), "--dry-run"]),
        )

    def test_normalization_overlap_and_adapters(self) -> None:
        self.assertEqual(
            crawl.canonicalize_url(
                "HTTPS://Official.Example:443/news//item/?utm_source=x&b=2&a=1#part"
            ),
            "https://official.example/news/item?a=1&b=2",
        )
        self.assertEqual(len([raw_official()]), 1)
        sec = sources_payload()["sources"][2]
        records = crawl.parse_sec_submissions(
            json.loads((FIXTURES / "sec_submissions.json").read_text()),
            sec,
            sec["machine_endpoint"],
            crawl.dt.datetime(2000, 1, 1, tzinfo=crawl.dt.timezone.utc),
        )
        self.assertEqual(len(records), 1)
        self.assertIn("/Archives/edgar/data/123456/", records[0].url)

    def test_source_gate_and_dedup(self) -> None:
        official, news, _ = sources_payload()["sources"]
        self.assertTrue(
            crawl.publication_gate(official, "https://alpha-sense.com/item")[0]
        )
        self.assertFalse(crawl.publication_gate(news, "https://techcrunch.com/item")[0])
        discovery = raw_official()
        discovery.url = "https://techcrunch.com/item"
        destination, candidate = crawl.normalize_item(discovery, news, NOW)
        self.assertEqual(destination, "candidate")
        self.assertEqual(candidate["verification_status"], "unverified")
        event = seeded_event()
        duplicate = copy.deepcopy(event)
        duplicate["id"] = "evt-2026-08-31-replacement"
        duplicate["primary_url"] += "?utm_source=duplicate"
        merged = crawl.merge_records([event], [duplicate], "events")
        self.assertEqual([event["id"]], [item["id"] for item in merged])

    def test_declared_user_agent_and_conditionals(self) -> None:
        seen: list[Any] = []

        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}
            def read(self, _limit: int = -1) -> bytes:
                return b"{}"
            def geturl(self) -> str:
                return "https://api.example/data"
            def getcode(self) -> int:
                return 200

        def opener(request: Any, timeout: float) -> Response:
            seen.append((request, timeout))
            return Response()

        client = crawl.HttpClient(
            user_agent="Radar-Test/1.0", opener=opener, sleeper=lambda _: None, retries=0
        )
        client.get(
            "https://api.example/data",
            {"id": "test", "rate_limit": {"requests_per_minute": 6000}},
            {"etag": '"old"', "last_modified": "Mon, 31 Aug 2026 00:00:00 GMT"},
        )
        request = seen[0][0]
        self.assertEqual(request.get_header("User-agent"), "Radar-Test/1.0")
        self.assertEqual(request.get_header("If-none-match"), '"old"')
        self.assertIsNotNone(request.get_header("If-modified-since"))

    def test_failure_preservation_routing_validation_and_build_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_repo(root)
            before = (root / "data/events.json").read_text()
            summary = crawl.run_pipeline(
                root / "config/sources.json",
                root / "data/events.json",
                root / "data/candidates.json",
                root / "data/.crawl-state.json",
                now=NOW,
                client=MemoryClient({}, {"official-feed"}),
                selected_sources={"official-feed"},
            )
            self.assertEqual(summary.sources_failed, 1)
            self.assertEqual(before, (root / "data/events.json").read_text())

            bodies = {
                "official-feed": (FIXTURES / "official_feed.xml").read_bytes(),
                "news-feed": (FIXTURES / "discovery_feed.xml").read_bytes(),
                "sec-filings": (FIXTURES / "sec_submissions.json").read_bytes(),
            }
            summary = crawl.run_pipeline(
                root / "config/sources.json",
                root / "data/events.json",
                root / "data/candidates.json",
                root / "data/.crawl-state.json",
                now=NOW,
                overlap_hours=20000,
                client=MemoryClient(bodies),
            )
            self.assertEqual(summary.events_added, 1)
            self.assertEqual(summary.candidates_added, 1)
            report = validate.validate_repository(root)
            self.assertTrue(report.ok, "\n".join(map(str, report.issues)))

            events = json.loads((root / "data/events.json").read_text())
            candidates = json.loads((root / "data/candidates.json").read_text())
            stable_events = (root / "data/events.json").read_bytes()
            stable_candidates = (root / "data/candidates.json").read_bytes()
            crawl.run_pipeline(
                root / "config/sources.json",
                root / "data/events.json",
                root / "data/candidates.json",
                root / "data/.crawl-state.json",
                now=NOW,
                client=MemoryClient(bodies),
            )
            self.assertEqual(stable_events, (root / "data/events.json").read_bytes())
            self.assertEqual(
                stable_candidates,
                (root / "data/candidates.json").read_bytes(),
            )
            build_event_fields = {
                "id", "slug", "type", "title", "company_ids", "country",
                "sectors", "event_date", "published_at", "summary", "primary_url",
                "publisher", "source_id", "source_tier", "retrieved_at",
                "verification_status", "provenance", "content_hash",
            }
            build_candidate_fields = {
                "id", "slug", "type", "title", "company_ids", "country",
                "sectors", "event_date", "published_at", "summary", "discovery_url",
                "publisher", "source_id", "source_tier", "retrieved_at",
                "verification_status", "verification_notes", "content_hash",
            }
            self.assertTrue(all(build_event_fields <= set(item) for item in events["events"]))
            self.assertTrue(all(build_candidate_fields <= set(item) for item in candidates["candidates"]))

    def test_validation_catches_ids_references_confidence_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_repo(root)
            payload = json.loads((root / "data/events.json").read_text())
            broken = copy.deepcopy(payload["events"][0])
            broken["company_ids"] = ["missing"]
            broken["confidence"] = 1.5
            broken["content_hash"] = "bad"
            payload["events"].append(broken)
            (root / "data/events.json").write_text(json.dumps(payload))
            report = validate.validate_repository(root)
            messages = "\n".join(map(str, report.issues))
            self.assertIn("duplicate event ID", messages)
            self.assertIn("unknown company", messages)
            self.assertIn("between 0 and 1", messages)
            self.assertIn("SHA-256", messages)


if __name__ == "__main__":
    unittest.main()
