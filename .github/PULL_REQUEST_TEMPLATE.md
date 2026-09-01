## Summary

<!-- What changes, and why? Link the related issue when applicable. -->

## Change type

- [ ] Company, product, or event data
- [ ] Correction
- [ ] Source adapter or pipeline
- [ ] Site or documentation
- [ ] Tests or maintenance

## Evidence and provenance

<!-- Required for record changes. Link primary evidence and map each changed factual field to the supporting source. Reputable media can aid discovery but cannot replace primary evidence for auto-publication. Write “Not applicable” for code-only changes. -->

Primary source URL(s):

Evidence-to-field mapping:

## Validation

<!-- Check every command you ran. Explain any unchecked item. -->

- [ ] `python scripts/validate.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] `python scripts/build_site.py --output-dir dist --base-url https://yzc-666.github.io/ai-finance-radar/`
- [ ] I reviewed the generated `dist/` output relevant to this change.

## Contributor checklist

- [ ] Facts are narrowly stated and editorial context is labeled separately.
- [ ] Dates, publishers, direct source URLs, and retrieval metadata are present where required.
- [ ] I did not add full copyrighted articles, paywalled material, secrets, or unnecessary personal data.
- [ ] Data changes preserve stable record IDs and document corrections instead of silently rewriting history.
- [ ] I disclosed relevant affiliations or conflicts in the PR description.
- [ ] I agree that my code contribution is provided under MIT and my eligible original dataset contribution under CC BY 4.0, as described in `CONTRIBUTING.md`.
