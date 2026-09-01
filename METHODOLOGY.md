# Methodology

AI × Finance Radar is a source-linked research dataset and public index of how artificial intelligence is being used in financial services in China and the United States. This document defines what can enter the Radar, how source provenance is evaluated, and how records are corrected.

The methodology verifies that a published claim is traceable to the cited source and represented faithfully. It does not guarantee that every underlying statement made by a source is independently true, and it does not claim complete market coverage.

## Scope and inclusion criteria

A company or product is eligible when public evidence supports all of the following:

1. **Material AI component.** AI or machine learning is part of the product or operating capability, not merely incidental wording.
2. **Material finance connection.** The product is built for, sold into, regulates, or operates within a financial-services workflow such as banking, capital markets, payments, lending, insurance, fraud, AML/KYC, compliance, financial research, or financial infrastructure.
3. **Relevant geography.** The organization, product, customer, or event has a clear connection to China or the United States. Cross-border records may carry both geographies.
4. **Publicly inspectable evidence.** At least one direct source URL supports the fields being published.
5. **Minimum record quality.** Required identifiers, dates, source metadata, categories, and a narrowly written factual summary pass the schema and integrity checks.

An event must additionally describe a material, dated change:

- **Funding:** a financing event supported by a directly involved party or official filing. A filing is not described as regulatory approval or proof that a round closed.
- **Product:** a launch or material availability or capability change.
- **Partnership:** an agreement publicly announced by a directly involved organization.
- **Customer:** a named pilot or deployment, using only the status stated by the source.
- **Acquisition:** an announced or completed acquisition, with status preserved.
- **Regulation:** a rule, filing, enforcement action, license, or official policy development relevant to AI in finance.

Generic marketing pages, undated capability claims, predictions, opinion pieces, job postings, and minor website edits are not events by themselves. “Partnership,” “pilot,” “customer,” and “production deployment” are not interchangeable.

## Source hierarchy

### Tier 1 — primary evidence

Primary evidence includes:

- regulator, court, legislature, central bank, or government publications;
- required filings and official transaction documents;
- official company newsrooms, product documentation, investor-relations material, or named executive statements; and
- official publications from a directly involved financial institution or counterparty.

Tier 1 establishes attributable evidence for publication. A first-party company statement is still a self-reported claim; its presence verifies provenance, not independent truth.

### Tier 2 — reputable media, discovery only

Reputable news organizations and specialist trade publications can reveal candidate records, add context, or point to primary documents. A Tier 2 source alone does not satisfy the automatic-publication gate. If no primary evidence can be located, the item remains a candidate or is excluded.

### Tier 3 — community submission, candidate only

Issues, pull requests, tips, social posts, newsletters, and other community submissions enter as leads. They are not evidence merely because they are public or widely repeated. A submission must link primary evidence before it can qualify for normal publication.

Anonymous claims, scraped aggregators, AI-generated summaries, copied databases, search-result snippets, and unsourced social posts are not accepted as evidence.

## Collection and publication flow

1. Source adapters poll documented feeds, APIs, and allowlisted public pages with an overlap window.
2. New items are normalized into candidate records with source, date, retrieval, and fingerprint metadata.
3. Exact and near-duplicate checks compare candidates with existing stable records.
4. Schema and integrity validation check required fields, controlled vocabulary, identifiers, URL policy, timestamps, and relationships.
5. The publication gate routes eligible Tier 1 records to the published dataset and everything else to review or rejection.
6. Tests and the deterministic site build must pass before generated data is committed or deployed.

A source failure must not erase previously published records. Collection respects source terms, documented APIs, robots controls, and practical rate limits. The project does not bypass authentication, CAPTCHAs, or paywalls.

## Automatic-publication gate

Automation may publish a record only when every applicable condition passes:

- the evidence is Tier 1 and the source owner is directly relevant to the claim;
- the source URL is direct, public, and from an allowlisted official domain;
- each factual field is supported by the cited material without inference beyond the source;
- required source publisher, source type, publication date when available, retrieval time, and content fingerprint are present;
- event date, geography, organizations, event type, and stable ID satisfy the schema;
- fact text contains no unlabeled analysis, recommendation, or promotional embellishment;
- duplicate and conflict checks find no unresolved match; and
- validation, offline tests, and deterministic generation all succeed.

Failure of any condition is fail-closed: the record remains a candidate for human review. Passing this gate means that provenance and representation checks passed. It is not a certification of the underlying company, product, transaction, or claim.

## Facts and context

Published factual summaries state only what the cited evidence supports. Wording preserves meaningful qualifications such as “announced,” “expects,” “pilot,” “subject to approval,” or “undisclosed.”

Explanatory analysis belongs in a separate, visibly labeled context field. Context may describe category relevance, prior events, or open questions, but it must not introduce new facts without sources. Generated summaries are never treated as sources.

## Dates and timestamps

Dates have distinct meanings and must not be silently substituted:

- `event_date`: when the underlying event occurred, if disclosed;
- `source_published_at`: when the source was published or filed;
- `retrieved_at`: when the project fetched the source;
- `first_seen_at`: when the Radar first observed the candidate; and
- `updated_at`: when the normalized record last changed.

Machine timestamps use ISO 8601 and UTC. Date-only values remain date-only when the source gives no time. Unknown dates stay unknown rather than being inferred from crawl time. The interface should display the relevant timezone or label a date as source-reported.

## Identity, fingerprints, and deduplication

Stable record IDs survive editorial corrections. Canonical URLs remove tracking parameters while retaining the original evidence URL where needed. Content fingerprints help identify changed or repeated source material; they do not prove authorship or truth.

Exact matches use stable IDs, canonical source URLs, and fingerprints. Near-duplicate review considers the principal organizations, event type, event date, product, and source language. Multiple sources describing one event are attached to one record when possible. Distinct stages—such as announcement, regulatory approval, and transaction close—may remain separate events when each has independent significance.

## Corrections and contested records

Anyone may open the correction issue form with a record ID, proposed change, and primary evidence. Maintainers:

1. compare the current field and proposed correction with the strongest available primary sources;
2. preserve the record ID and Git history;
3. change only the fields the evidence supports;
4. update source and timestamp metadata;
5. document the correction reason in the change history; and
6. mark a record as corrected, superseded, or withdrawn when deletion would hide useful history.

Conflicting primary sources are disclosed and routed to review. The project may temporarily withhold a contested record rather than imply certainty. Broken links may be supplemented with an official replacement or lawful archive, but an archive does not upgrade a weak source tier.

## Limitations

- Coverage is selective, evolves over time, and depends on public disclosure and accessible sources.
- China–United States coverage does not represent the full global market.
- Sources vary by language, legal regime, disclosure practice, and publication speed.
- Private transactions, internal deployments, failed pilots, and negative outcomes are systematically underreported.
- China coverage can be delayed when an official portal has no documented reusable feed or a company announcement lacks a stable public URL.
- Private financing coverage excludes broader commercial databases whose terms do not permit scraping or republication.
- Company statements can be accurate records of what a company announced while still being incomplete, promotional, or later revised.
- Classification choices and deduplication involve editorial judgment even when rules are explicit.
- Sources can move, disappear, or change after retrieval; fingerprints and timestamps reduce but do not eliminate that risk.
- The update schedule does not make the dataset real-time.

The Radar is a starting point for research, not a substitute for original documents, professional diligence, or domain expertise.

## No investment advice

Nothing in the repository, dataset, generated site, or community discussion is investment, legal, accounting, tax, compliance, or other professional advice. Inclusion is not endorsement; omission is not a negative assessment. Do not make financial decisions from the Radar without independent research and qualified advice.

## Reuse

Eligible original curated dataset material is licensed as described in [DATA_LICENSE.md](DATA_LICENSE.md). Source publications, quotations, names, trademarks, and linked third-party material retain their original rights and restrictions.
