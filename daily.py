"""Daily READ-ONLY reconciliation. Human approval remains exclusive to app."""
import json
import sys
from bellhaven.pipeline import refresh

if __name__ == "__main__":
    try:
        result = refresh()
        print(json.dumps({"as_of": result["refreshed_at"], "website_stats": result["website_stats"], "counts": result["counts"]}, indent=2))
    except Exception as exc:
        print(f"Daily audit failed safely: {exc}", file=sys.stderr)
        raise SystemExit(1)
