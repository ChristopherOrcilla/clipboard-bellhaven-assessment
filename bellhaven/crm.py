"""Single place for API integration. Confirm endpoints/auth with /api/docs.

No write call happens in scraping, matching, CLI daily mode, or refresh.
"""
import os
from urllib.parse import urljoin
import requests
from dotenv import load_dotenv
load_dotenv()


class CRMError(RuntimeError):
    pass


class CRMClient:
    def __init__(self, token=None):
        self.base = os.getenv("CRM_BASE_URL", "https://analyst-assessment-production.up.railway.app/api/v1").rstrip("/")
        self.path = os.getenv("CRM_ACCOUNTS_PATH", "/accounts")
        self.token = token or os.getenv("CRM_TOKEN", "")
        self.auth_style = os.getenv("CRM_AUTH_STYLE", "bearer").lower().strip()
        self.update_method = os.getenv("CRM_UPDATE_METHOD", "PATCH").upper()
        self.create_method = os.getenv("CRM_CREATE_METHOD", "POST").upper()
        self.page_size = int(os.getenv("CRM_PAGE_SIZE", "100"))
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        if self.token and self.token != "PASTE_YOUR_PRIVATE_TOKEN_HERE":
            if self.auth_style == "bearer":
                self.s.headers["Authorization"] = f"Bearer {self.token}"
            elif self.auth_style == "x-api-key":
                self.s.headers["X-API-Key"] = self.token
            elif self.auth_style == "x-api-token":
                self.s.headers["X-API-Token"] = self.token
            elif self.auth_style == "token":
                self.s.headers["Authorization"] = f"Token {self.token}"
            else:
                raise CRMError("Unsupported CRM_AUTH_STYLE; choose bearer, token, x-api-key, or x-api-token")

    def req(self, method, path, **kwargs):
        url = self.base + "/" + path.lstrip("/")
        try:
            r = self.s.request(method, url, timeout=25, **kwargs)
        except requests.RequestException as e:
            raise CRMError(f"CRM connection failed: {type(e).__name__}: {e}") from e
        if not r.ok:
            # Never include Authorization headers in exceptions, logs, or videos.
            raise CRMError(f"CRM {method} {path}: HTTP {r.status_code}; response: {r.text[:500]}")
        if r.status_code == 204 or not r.content:
            return {}
        try:
            return r.json()
        except ValueError as e:
            raise CRMError(f"CRM {method} {path} did not return JSON") from e

    @staticmethod
    def _unpack(data):
        if isinstance(data, list):
            return data, {}
        if not isinstance(data, dict):
            raise CRMError(f"Unexpected accounts response: {type(data).__name__}")
        meta = data
        for key in ("accounts", "items", "results", "records"):
            if isinstance(data.get(key), list):
                return data[key], meta
        if isinstance(data.get("data"), list):
            return data["data"], meta
        if isinstance(data.get("data"), dict):
            for key in ("accounts", "items", "results", "records"):
                if isinstance(data["data"].get(key), list):
                    return data["data"][key], {**data, **data["data"]}
        raise CRMError("Account list schema is unrecognized. Check Swagger docs; adjust CRMClient._unpack before writes")

    def accounts(self):
        records, seen = [], set()
        params = {"limit": self.page_size, "page": 1}
        for page_num in range(1, 51):
            data = self.req("GET", self.path, params=params)
            batch, meta = self._unpack(data)
            fresh = [row for row in batch if str(row.get("id", "")) not in seen]
            for row in fresh:
                if not row.get("id"):
                    raise CRMError("Account with no id; cannot safely reconcile")
                seen.add(str(row["id"]))
            records.extend(fresh)
            total = meta.get("total") or meta.get("total_count") or meta.get("count")
            if total is not None:
                try:
                    if len(records) >= int(total):
                        return records
                except (ValueError, TypeError):
                    pass
            next_cursor = meta.get("next_cursor") or meta.get("nextCursor")
            if next_cursor:
                params = {"limit": self.page_size, "cursor": next_cursor}
            elif meta.get("next_page"):
                params = {"limit": self.page_size, "page": meta["next_page"]}
            elif meta.get("has_more") or meta.get("hasMore"):
                params = {"limit": self.page_size, "page": page_num + 1}
            elif len(batch) >= self.page_size and len(fresh) == len(batch):
                params = {"limit": self.page_size, "page": page_num + 1}
            else:
                return records
            if not fresh:
                raise CRMError("CRM pagination appears to repeat a page. Aborting rather than using an incomplete list")
        raise CRMError("CRM pagination exceeded 50 pages; inspect API schema")

    def get_account(self, id):
        data = self.req("GET", f"{self.path.rstrip('/')}/{id}")
        if not isinstance(data, dict):
            raise CRMError("Unexpected account detail response")
        return data.get("account", data.get("data", data))

    def patch_account(self, id, fields):
        if not fields:
            raise CRMError("Refusing empty patch")
        return self.req(self.update_method, f"{self.path.rstrip('/')}/{id}", json=fields)

    def create_account(self, fields):
        if not fields.get("name") or not fields.get("parent_id"):
            raise CRMError("New account must have a name and correct parent")
        return self.req(self.create_method, self.path, json=fields)


def prop(a, key):
    keys = {
        "name": ("name", "account_name"),
        "street": ("billing_street", "street", "address", "address_line1"),
        "city": ("billing_city", "city"),
        "state": ("billing_state", "state"),
        "zip": ("billing_postal_code", "billing_zip", "postal_code", "zip", "zip_code"),
        "care_type": ("care_type",),
        "parent_id": ("parent_id",),
        "note": ("note",),
        "status": ("status",),
        "lifetime_revenue": ("lifetime_revenue",),
        "outstanding_ar": ("outstanding_ar",),
        "chow_current_account": ("chow_current_account",),
        "duplicate_of_account": ("duplicate_of_account",),
    }[key]
    for k in keys:
        if k in a:
            return a.get(k)
    return None


def write_field(a, key):
    choices = {"street": ("billing_street", "street"), "city": ("billing_city", "city"), "state": ("billing_state", "state"), "zip": ("billing_postal_code", "billing_zip", "postal_code", "zip", "zip_code")}
    if key not in choices:
        return key
    for k in choices[key]:
        if k in a:
            return k
    if key == "zip":
        cfg = os.getenv("CRM_ZIP_WRITE_FIELD", "auto")
        return "billing_postal_code" if cfg == "auto" else cfg
    return {"street": "billing_street", "city": "billing_city", "state": "billing_state"}[key]


def new_account_payload(facility, parent_id, sample_account=None):
    sample_account = sample_account or {}
    d = {"name": facility["name"], "parent_id": parent_id, "status": "Active"}
    for field in ("street", "city", "state", "zip"):
        d[write_field(sample_account, field)] = facility[field]
    care = map_care(facility.get("care_offerings", []))
    if care:
        d["care_type"] = care
    d["note"] = f"Created from Bellhaven location directory: {facility['source_url']}. Care offerings: {', '.join(facility.get('care_offerings', []))}."
    return d


def map_care(offerings):
    if not offerings:
        return None
    types = {"Short-Term Rehabilitation & Nursing": "Skilled Nursing", "Memory Support": "Memory Care", "Assisted Living": "Assisted Living", "Independent Living": "Independent Living"}
    for label in offerings:
        for src, dest in types.items():
            if src.casefold() in label.casefold():
                return dest
    return None
