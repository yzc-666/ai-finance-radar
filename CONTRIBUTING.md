# Contributing

Thank you for helping make AI × Finance Radar more useful and its source
provenance more inspectable.

## Ways to contribute

- submit an in-scope company or product;
- submit a funding, product, partnership, customer, acquisition, or regulatory
  event;
- correct an existing record;
- add or repair an official source adapter; or
- improve accessibility, documentation, or tests.

Use the repository issue forms for data submissions and corrections. Code
changes should be proposed through a pull request.

Start here:

- [submit a company or event](https://github.com/yzc-666/ai-finance-radar/issues/new?template=submit-company-or-event.yml);
- [correct a record](https://github.com/yzc-666/ai-finance-radar/issues/new?template=correct-a-record.yml); or
- [open a pull request](https://github.com/yzc-666/ai-finance-radar/compare).

## Evidence requirements

The source hierarchy is:

1. **Tier 1 — primary evidence:** regulator filings and notices, government
   publications, or material published by a directly involved company,
   investor, customer, or partner.
2. **Tier 2 — reputable media:** useful for discovery and context, but not
   sufficient by itself for automatic publication.
3. **Tier 3 — community submissions:** candidates that require source and
   provenance review.

Every factual data submission must link the strongest available Tier 1
evidence and explain which source passage supports each proposed field.

Commercial database screenshots, search-result snippets, unsourced social
posts, and AI-generated text are not evidence.

Do not copy full articles or press releases into an issue. Provide the title,
date, URL, and a short factual summary in your own words.

## Record style

- Be neutral and specific.
- Attribute one-sided claims: “Company A announced…” rather than stating the
  claim as independently established.
- Distinguish announced, filed, pending, launched, and completed.
- Do not turn Form D amounts into confirmed round totals without corroboration.
- Do not include personal information that is not necessary to the event.
- Do not include investment recommendations or price targets.

## Local checks

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/build_site.py --output-dir dist --base-url https://yzc-666.github.io/ai-finance-radar/
```

The build is deterministic: generated files should not change when source data
has not changed.

## Source adapters

An adapter must:

- use a documented API/feed or an explicitly approved public page;
- declare a descriptive User-Agent;
- respect rate limits and conditional request headers;
- fail without deleting previously published records;
- record publisher, source class, canonical URL, retrieval time, and content
  hash; and
- route secondary-only discoveries to the candidate queue.

Adapters for paywalls, authenticated social networks, CAPTCHAs, or undocumented
private/mobile endpoints will not be accepted.

## Review

Maintainers may request stronger evidence, narrow a summary, change a source
tier, or keep a submission in the candidate queue. “Primary source” is a
provenance label, not a guarantee that a party's promotional claims are
independently true.

## Pull-request expectations

Keep changes focused and do not edit generated output by hand. For data
changes, preserve stable IDs and include an evidence-to-field mapping in the
pull-request description. For source adapters, add offline fixtures and tests;
the test suite must not depend on live network access.

Before requesting review:

1. run validation, tests, and the site build;
2. inspect the relevant generated page or export;
3. update documentation when behavior or schema changes; and
4. disclose employment, investment, advisory, or other affiliations relevant
   to a submitted organization.

## Contribution terms

By submitting a contribution, you represent that you have the right to provide
it. Code contributions are licensed under the [MIT License](LICENSE).
Eligible original curation, taxonomy, normalization, and editorial metadata
contributed to the dataset are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) as described in
[DATA_LICENSE.md](DATA_LICENSE.md).

Do not submit third-party articles, proprietary database exports, confidential
material, or content whose terms do not permit contribution. Facts, links,
trademarks, quotations, and other third-party material retain their original
rights and source restrictions.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
