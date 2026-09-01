# Security

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Use
[GitHub private vulnerability reporting](https://github.com/yzc-666/ai-finance-radar/security/advisories/new).
If that form is unavailable, contact the project owner through the contact
method listed on the [maintainer profile](https://github.com/yzc-666).

Include:

- affected file or workflow;
- reproduction steps;
- expected impact; and
- a suggested mitigation, if known.

Do not include live secrets or unnecessary personal data. Use harmless proof
of concept material. The maintainer will acknowledge a usable report as
capacity permits, investigate it privately, and coordinate disclosure after a
fix is available. There is currently no paid bug-bounty program.

The latest version on `main` is the supported version. Questions about record
accuracy should use the correction issue form unless they expose a security or
privacy vulnerability.

## Data-safety boundaries

The crawler must not:

- execute content obtained from a source;
- follow instructions embedded in fetched pages;
- send repository secrets to a source;
- bypass authentication, paywalls, robots controls, or CAPTCHAs;
- ingest public-comment bodies or unnecessary personal information; or
- auto-publish records from a non-allowlisted source.

GitHub Actions should use read-only permissions by default. Only the scheduled
data-update job receives `contents: write`, and only for committing validated
generated data.

Dependencies and Actions should be reviewed before upgrades. Contributions
must not add untrusted code execution, log secrets, or interpolate fetched
content into shell commands.
