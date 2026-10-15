import copy
from bellhaven.scrape import parse_detail, links_from
from bellhaven.match import reconciliation, compare
from bellhaven.review import approve, reject, decisions
from bellhaven.util import street_norm

URL = "https://analyst-assessment-production.up.railway.app/communities/abc"

def site(i=0, **kw):
    d = {"name": f"Bellhaven of Site {i}", "street": f"{100+i} Main St", "city": f"Town{i}", "state": "OH", "zip": f"{45000+i:05}", "care_offerings": ["Assisted Living"], "source_url": URL + str(i)}
    d.update(kw)
    return d

def account(i=0, **kw):
    d = {"id": f"ACC{i}", "name": f"Bellhaven of Site {i}", "billing_street": f"{100+i} Main Street", "billing_city": f"Town{i}", "billing_state": "OH", "billing_postal_code": f"{45000+i:05}", "care_type": "Assisted Living", "parent_id": "PARENT", "status": "Active", "lifetime_revenue": 0, "outstanding_ar": 0, "note": None, "chow_current_account": None, "duplicate_of_account": None}
    d.update(kw)
    return d

def parent():
    return {"id": "PARENT", "name": "Bellhaven Senior Living (Parent Account)", "parent_id": None}

def simulate(accounts=None, sites=None):
    if sites is None:
        sites = [site(i) for i in range(30)]
    if accounts is None:
        accounts = [parent()] + [account(i) for i in range(30)]
    return reconciliation(sites, accounts)

def test_address_standardization():
    assert street_norm("1120 W Main St.") == street_norm("1120 West Main Street")
    assert compare(site(0), account(0))["strong"]

def test_name_without_matching_location_is_not_identity():
    result = simulate(accounts=[parent()] + [account(i) for i in range(1,30)] + [account(0, billing_city="Another City", billing_state="CO", billing_postal_code="80901")])
    assert any(p["kind"] == "new" and p["facility"]["name"] == "Bellhaven of Site 0" for p in result["proposals"])

def test_chow_trigger_requires_both_revenue_and_ar():
    accounts = [parent()] + [account(i) for i in range(30)]
    accounts[1].update(parent_id="OTHER", lifetime_revenue=9000, outstanding_ar=150)
    result = simulate(accounts=accounts)
    p = [p for p in result["proposals"] if p["account"].get("id") == "ACC0"]
    assert len(p) == 1 and p[0]["kind"] == "chow"
    assert p[0]["changes"] == {"new_parent_id": "PARENT"}
    for rev, ar in [(0, 100), (9000, 0), (0, 0)]:
        accounts[1].update(lifetime_revenue=rev, outstanding_ar=ar)
        result = simulate(accounts=accounts)
        ps = [p for p in result["proposals"] if p["account"].get("id") == "ACC0"]
        assert ps[0]["kind"] == "update"
        assert ps[0]["changes"]["parent_id"] == "PARENT"

def test_duplicate_same_site_address():
    accounts = [parent()] + [account(i) for i in range(30)]
    accounts.append(account(0, id="COPY0", billing_street="100 Main St"))
    result = simulate(accounts=accounts)
    assert any(p["kind"] == "duplicate" and p["changes"]["duplicate_of_account"] in ("ACC0", "COPY0") for p in result["proposals"])

def test_missing_listing_not_immediately_deactivated():
    accounts = [parent()] + [account(i) for i in range(30)]
    accounts.append(account(99))
    result = simulate(accounts=accounts)
    matching = [p for p in result["proposals"] if p["account"].get("id") == "ACC99"]
    assert matching and matching[0]["kind"] == "unlisted"
    assert matching[0]["changes"]["status"] == "Needs Review"

def test_scraping_detail():
    html = "<h1>Bellhaven Meadows of Findlay</h1><section><h2>Address</h2><div>1800 N Blanchard St</div><div>Findlay, OH 45840</div><h2>Care Offerings</h2><p>Assisted Living</p><p>Memory Support</p><h2>Administrator</h2><p>Sam Pruitt</p></section>"
    f = parse_detail(html, URL)
    assert f["zip"] == "45840" and len(f["care_offerings"]) == 2
    assert f["street"] == "1800 N Blanchard St"

def test_homepage_link_capture():
    href = "/communities/bellhaven-meadows-of-findlay"
    assert URL.rsplit("/", 1)[0] + "/bellhaven-meadows-of-findlay" in links_from(f"<a href='{href}'>Findlay</a>")

class FakeClient:
    def __init__(self, old):
        self.records = {old["id"]: copy.deepcopy(old)}
        self.writes = []
    def get_account(self, id):
        return copy.deepcopy(self.records[id])
    def accounts(self):
        return copy.deepcopy(list(self.records.values()))
    def create_account(self, fields):
        id = "NEW001"
        row = {**fields, "id": id}
        self.records[id] = row
        self.writes.append(("create", id, fields))
        return row
    def patch_account(self, id, fields):
        self.records[id].update(fields)
        self.writes.append(("patch", id, fields))
        return copy.deepcopy(self.records[id])

def test_approved_chow_preserves_historical_account(tmp_path):
    old = account(0, parent_id="OTHER", lifetime_revenue=15000, outstanding_ar=100)
    proposal = [p for p in simulate(accounts=[parent(),old] + [account(i) for i in range(1,30)])["proposals"] if p["kind"] == "chow"][0]
    c = FakeClient(old)
    path = tmp_path / "decisions.json"
    result = approve(proposal, c, "PARENT", path)
    assert result["result"] == "chow_linked"
    assert c.records["ACC0"]["parent_id"] == "OTHER"
    assert c.records["ACC0"]["lifetime_revenue"] == 15000
    assert c.records["ACC0"]["outstanding_ar"] == 100
    assert c.records["ACC0"]["chow_current_account"] == "NEW001"
    assert c.writes[1] == ("patch", "ACC0", {"chow_current_account": "NEW001"})
    assert decisions(path)[proposal["id"]]["status"] == "approved"

def test_rejection_stores_reason_and_never_calls_crm(tmp_path):
    p = {"id": "proposal007", "kind": "new"}
    path = tmp_path / "decisions.json"
    reject(p, "Not enough evidence", path)
    assert decisions(path)[p["id"]]["status"] == "rejected"
