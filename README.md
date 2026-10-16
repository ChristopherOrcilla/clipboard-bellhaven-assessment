# Bellhaven Senior Living — CRM Reconciliation

A human-in-the-loop, evidence-backed pipeline for the Clipboard Health analyst assessment.

**What it does:** Crawls every paginated Bellhaven community listing *plus homepage-only promotions*, compares facilities against all CRM accounts, generates auditable ownership and cleanup proposals, enforces CHOW billing protection, and provides a Streamlit reviewer who must explicitly approve any CRM writes. A daily GitHub Actions workflow is read-only.

## File map

- `bellhaven/scrape.py`: multi-page and homepage crawl, addresses/care extraction.
- `bellhaven/crm.py`: token, authentication, pagination, GET/POST/PATCH API adapter.
- `bellhaven/match.py`: deterministic confidence and suggested changes.
- `bellhaven/review.py`: approval, reject, optimistic checks, CHOW transaction checkpoint.
- `bellhaven/pipeline.py`: refresh data and filter previously decided items.
- `app.py`: local review UI.
- `daily.py`, `.github/workflows/daily-readonly.yml`: daily read-only schedule, no automatic approval.
- `state/decisions.json`: synced decision history.
- `tests/`: offline safety tests.
