# AI × Finance Radar

AI × Finance Radar is an open, source-linked map of how artificial intelligence is entering financial services in China and the United States.

Explore the project at **<https://yzc-666.github.io/ai-finance-radar/>**.

The Radar connects companies and concrete products with funding, launches, partnerships, deployments, acquisitions, and regulatory events. Each published factual summary points to primary evidence and exposes source metadata so readers can inspect its provenance. Secondary reporting and community tips remain candidates until the publication requirements are met.

The goal is a useful, correctable public research record—not the largest database and not a claim of complete coverage. Read the [product vision](VISION.md) and [methodology](METHODOLOGY.md).

## Why this exists

AI-finance information is fragmented across regulator sites, filings, company newsrooms, official feeds, and media coverage. Commercial datasets can be expensive or difficult to audit. The Radar makes a narrower promise: published records are attributable, source-linked, downloadable, and open to correction.

Source provenance does not certify that every statement made by a source is independently true. First-party announcements remain attributed first-party claims.

## Run locally

The pipeline targets Python 3.12 and uses repository-local data. Validation and tests are offline.

```bash
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py --output-dir dist --base-url https://yzc-666.github.io/ai-finance-radar/
python3 -m http.server --directory dist 8000
```

Open <http://localhost:8000/>.

To perform a network-enabled refresh before validating and building:

```bash
python3 scripts/crawl.py
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py --output-dir dist --base-url https://yzc-666.github.io/ai-finance-radar/
```

An individual source failure must not erase existing published records. The scheduled update uses an overlap window, validates all resulting records, runs the offline tests, and builds deterministic output before committing eligible data changes.

## Architecture and data flow

```text
Tier 1 official sources ─┐
Tier 2 discovery media ──┼─> crawl ─> normalize/dedupe ─> candidate records
Community submissions ───┘                         │
                                                   v
                                      provenance publication gate
                                      │                       │
                                      v                       v
                              published datasets       review candidates
                                      │
                                      v
                              validate ─> test ─> build
                                      │
                                      v
                           static pages + JSON/CSV/RSS
                                      │
                                      v
                                  GitHub Pages
```

Key directories and files:

```text
.
├── index.html, companies.html, methodology.html  # static page sources
├── assets/                                       # browser assets and icons
├── config/                                       # source registry, policy, and JSON schemas
├── data/                                         # normalized records and candidates
├── scripts/
│   ├── crawl.py                                  # collection and routing
│   ├── validate.py                               # provenance/integrity checks
│   └── build_site.py                             # deterministic generation
├── tests/                                        # offline pipeline tests
├── dist/                                         # ignored Pages build artifact
└── .github/workflows/                            # CI, updates, and deployment
```

The normalized public datasets are `data/companies.json` and `data/events.json`. Items that still need evidence or review are separated in `data/candidates.json`; the build emits CSV views to `dist/data/exports/`.

## Source policy

- **Tier 1 — primary evidence:** official regulators, courts, governments, filings, and directly involved company or institution publications. Only qualifying Tier 1 evidence can pass the automatic-publication gate.
- **Tier 2 — reputable media:** discovery and context only. A media-only item stays in the candidate queue.
- **Tier 3 — community submission:** a lead that must undergo the same evidence, provenance, schema, and deduplication checks as an automated candidate.

Facts and editorial context are stored and displayed separately. Passing the gate means source and representation checks succeeded; it is not an endorsement or a guarantee of the underlying claim. See [METHODOLOGY.md](METHODOLOGY.md) for the full inclusion, timestamp, deduplication, and correction rules.

## Contribute

Domain expertise, corrections, source adapters, tests, accessibility fixes, and documentation improvements are welcome.

- [Submit a company or event](https://github.com/yzc-666/ai-finance-radar/issues/new?template=submit-company-or-event.yml)
- [Correct an existing record](https://github.com/yzc-666/ai-finance-radar/issues/new?template=correct-a-record.yml)
- Read the [contribution guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md)

Data submissions need direct primary evidence and a clear mapping from the source to each proposed factual field. Do not submit full articles, proprietary database exports, confidential information, or unnecessary personal data.

## License and disclaimer

Repository code is licensed under the [MIT License](LICENSE). To the extent applicable, project-authored dataset selection, normalization, taxonomy, and original editorial metadata are available under [CC BY 4.0](DATA_LICENSE.md). Third-party facts, names, trademarks, links, quotations, and source materials retain their original rights and source restrictions.

AI × Finance Radar is for research and discovery only. It is not investment, legal, tax, accounting, compliance, or other professional advice. Inclusion is not endorsement, and omission is not a negative assessment. Coverage may be incomplete, delayed, or changed through the documented correction process.
