# Vision

## The public memory of AI in finance

AI × Finance Radar should become the most inspectable public record of how
artificial intelligence is entering financial services.

It is not a leaderboard, a stream of promotional announcements, or a source of
trading recommendations. It is a continuously maintained map connecting four
things:

1. the companies building AI for finance;
2. the products they actually ship;
3. the financing, partnerships, deployments, acquisitions, and regulatory
   events that change the landscape; and
4. the original evidence behind each claim.

The core product promise is simple:

> If the Radar says something happened, the reader can see who said it, when it
> was said, what kind of source it is, and how the record has changed.

## Who it serves

### Financial institutions

Innovation, data, compliance, risk, and procurement teams can discover vendors
by workflow instead of searching through generic AI lists. Product pages make
it easier to distinguish a model demo from a deployable product and an
announced partnership from a source-documented customer deployment.

### Founders and operators

Teams can track competitor launches, category formation, distribution
partnerships, regulatory constraints, and whitespace across China and the
United States.

### Investors and analysts

The Radar offers diligence leads and market structure, not buy or sell
signals. Source-linked timelines help an analyst identify what deserves deeper
investigation.

### Researchers, journalists, and policymakers

Downloadable records, stable IDs, source metadata, and Git history create a
citable longitudinal dataset about AI adoption in a regulated industry.

## Why people return

### Start with the delta

Most directories are useful once. A daily "What changed?" feed creates a
reason to return: new products, funding, partnerships, deployments,
acquisitions, and policy events.

### Organize around financial work

Users browse by real workflows—research, trading, credit, fraud, AML/KYC,
compliance, insurance, customer service, and financial infrastructure—rather
than by vague labels such as "AI company."

### Make every page shareable

Each company and event receives a stable URL, concise summary, and visible
evidence. Readers can share a record without asking others to trust a
screenshot.

### Keep access open

The site, normalized JSON, CSV exports, RSS feed, source registry, and change
history remain public. GitHub Issues provide a low-friction route to submit a
missing company or challenge a record.

## Attraction loops

The product should grow through usefulness rather than through inflated
coverage claims:

1. **Freshness loop:** scheduled collection creates a useful change feed;
   returning readers discover new records and subscribe to the RSS feed.
2. **Evidence loop:** every shareable record leads to its underlying source;
   readers can check the representation and report a stronger source or a
   correction.
3. **Contribution loop:** clear issue forms turn domain expertise into
   candidates; transparent review turns accepted candidates into durable
   public records.
4. **Reuse loop:** stable IDs and downloadable data let researchers build
   analyses; their citations and feedback expose gaps and improve the dataset.
5. **Discovery loop:** workflow, geography, company, and event pages make
   related records easier to find; useful pages attract more informed readers
   and contributors.

These loops depend on visible provenance and stable records. Traffic without
trust is not a product goal.

## How professionalism is maintained

The trust model is layered: automated schema and provenance checks prevent
obvious defects; conservative publication rules keep uncertain leads in a
candidate queue; visible source classes let readers judge evidence; and Git
history plus a public correction path make editorial decisions inspectable.
No layer claims to certify the underlying source's statement as true.

### Provenance before volume

A smaller record with a primary source is more valuable than a large,
untraceable scrape. Every published event must include its source URL,
publisher, source class, dates, retrieval time, and content fingerprint.

### Evidence classes are visible

Regulatory filings, regulator notices, and first-party announcements are
distinguished from secondary reporting. Secondary-only discoveries remain in
a review queue and are not presented as confirmed events.

### Facts and context are separate

The factual summary describes only what the evidence supports. Any explanation
of why an event matters is labeled as context, not blended into the reported
fact.

### Corrections are part of the product

Record IDs remain stable. Corrections preserve Git history, document the reason
for the change, and link to better evidence. The goal is not to appear
infallible; it is to be inspectably correctable.

### Legal and operational restraint

The crawler respects documented APIs, rate limits, robots controls, and source
terms. It does not bypass authentication, CAPTCHAs, or paywalls, and it does
not republish commercial databases or full copyrighted articles.

## Non-goals

The Radar is not:

- a comprehensive census of every AI or financial-services company;
- a real-time trading feed, valuation model, ranking, endorsement, or
  investment recommendation;
- a replacement for filings, regulator databases, professional diligence, or
  direct customer references;
- a repository of full articles, paywalled content, leaked material, personal
  data, or copied commercial datasets;
- a venue for rumors or a way to convert repeated secondary reporting into a
  primary fact; or
- an automated judge of whether a company's attributed statement is
  ultimately true.

## Roadmap

### Phase 1 — credible foundation

Ship the static public site, normalized company and event records, source
registry, candidate queue, schema validation, daily automation, RSS, CSV
exports, issue forms, and correction process. Establish conservative coverage
of representative China and United States sources before broadening volume.

### Phase 2 — better discovery

Improve workflow, geography, company, product, and event filtering. Add stable
detail pages, richer relationship links, source freshness signals, lawful
archival references, and clearer distinctions among announcement, pilot,
production use, and disclosed customer deployment.

### Phase 3 — analysis without obscuring facts

Add reproducible category and geography trends, company-to-product and
company-to-institution graphs, regulation-to-product mappings, and versioned
data releases. Analytical views must remain traceable to the underlying
records and visibly separate methodology from observation.

### Phase 4 — sustainable public infrastructure

Offer a versioned API if demand and maintenance capacity justify it, optional
digests, documented reviewer roles, service-level expectations for
corrections, and community maintainers with transparent ownership. Expansion
to other geographies should follow source expertise, not precede it.

## How success is measured

Success is not the largest row count. Useful measures include the share of
published records with direct primary evidence, validation and build
reliability, correction response time, source-link health, repeat use of the
change feed, responsible dataset reuse, and contributor acceptance quality.
The ultimate test is whether a reader can discover something important,
inspect its provenance quickly, understand its limits, and reuse the record
responsibly.
