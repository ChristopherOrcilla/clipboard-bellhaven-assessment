"""Refresh website & CRM into proposal file. NEVER writes to CRM."""
from collections import Counter
from .crm import CRMClient
from .match import reconciliation
from .scrape import scrape_all
from .review import decisions
from .util import save_json, load_json, utcnow

BUNDLE_PATH = "data/latest_run.json"


def refresh(client=None):
    client = client or CRMClient()
    website = scrape_all()
    accounts = client.accounts()
    result = reconciliation(website["facilities"], accounts)
    decided = decisions()
    result["proposals"] = [p for p in result["proposals"] if decided.get(p["id"], {}).get("status") not in {"approved", "rejected"}]
    result["counts"]["pending_review"] = len(result["proposals"])
    result["counts"]["by_kind"] = dict(Counter(p["kind"] for p in result["proposals"]))
    result["website_stats"] = website["stats"]
    result["refreshed_at"] = utcnow()
    save_json(BUNDLE_PATH, result)
    return result


def latest():
    return load_json(BUNDLE_PATH, {})
