# Data notes

The JSON files in this directory contain normalized factual metadata and short
original summaries. Linked articles, filings, product pages, trademarks, and
other source material remain subject to their publishers' terms.

Only allowlisted first-party company, regulator, or filing sources may enter
`events.json`. Secondary RSS discoveries are metadata-only leads and remain in
`candidates.json` until a primary source is found. The crawler does not store
article bodies, bypass paywalls, collect personal data, or produce investment
recommendations.

Company `country` values represent this MVP's market/headquarters
classification (China or the United States), not legal-incorporation advice.
The `last_verified_at` and provenance timestamps record the latest editorial
source check. A missing `founded_year` is preferred to an uncertain estimate.

Content hashes are SHA-256 digests of semantic record fields. Retrieval
timestamps and provenance transport metadata are excluded so the same source
item produces the same digest across deterministic offline runs.
