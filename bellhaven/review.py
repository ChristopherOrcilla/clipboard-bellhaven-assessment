"""Human-gated writes only. All mutations are called from explicit Approve button."""
from .crm import prop, new_account_payload, CRMError
from .match import compare
from .util import load_json, save_json, utcnow, money

DECISION_PATH = "state/decisions.json"


def decisions(path=DECISION_PATH):
    return load_json(path, {})


def record_decision(id, status, detail=None, path=DECISION_PATH):
    data = decisions(path)
    current = data.get(id, {})
    current.update({"status": status, "at": utcnow()})
    if detail:
        current.update(detail)
    data[id] = current
    save_json(path, data)
    return current


def reject(p, rationale, path=DECISION_PATH):
    if not rationale.strip():
        raise ValueError("Enter why you are rejecting this proposal")
    if decisions(path).get(p["id"], {}).get("status") == "approved":
        raise ValueError("Cannot reject an already-approved change")
    return record_decision(p["id"], "rejected", {"rationale": rationale.strip()}, path)


def _is_same_site(facility, acct):
    return compare(facility, acct)["strong"]


def _find_target(client, facility, parent_id):
    found = [a for a in client.accounts() if str(prop(a, "parent_id")) == str(parent_id) and _is_same_site(facility, a) and not prop(a, "duplicate_of_account")]
    if len(found) > 1:
        raise CRMError("Several matching accounts already exist under intended parent; stop and manually review duplicates")
    return found[0] if found else None


def _ensure_id(response):
    if isinstance(response, dict):
        for d in (response, response.get("account", {}), response.get("data", {})):
            if isinstance(d, dict) and d.get("id"):
                return str(d["id"])
    return None


def approve(p, client, parent_id, path=DECISION_PATH):
    pid = p["id"]
    past = decisions(path).get(pid, {})
    if past.get("status") in ("approved", "rejected"):
        raise CRMError(f"This proposal was already {past['status']}; no additional write performed")
    kind = p["kind"]
    site = p.get("facility", {})
    acct = p.get("account", {})
    changes = p.get("changes", {})

    if kind in {"update", "duplicate", "unlisted", "investigate"}:
        aid = acct.get("id")
        if not aid:
            raise CRMError("Missing account id; refuse update")
        live = client.get_account(aid)
        if str(live.get("id")) != str(aid):
            raise CRMError("Account id differs from expected id")
        if kind == "investigate":
            payload = {"status": "Needs Review", "note": str(prop(live, "note") or "") + f"\nBellhaven site/name conflict: {site.get('source_url', '')}. Human research required; no ownership change."}
        else:
            payload = dict(changes)
        if "parent_id" in payload and money(prop(live, "lifetime_revenue")) > 0 and money(prop(live, "outstanding_ar")) > 0:
            raise CRMError("BLOCKED by CHOW SOP: positive lifetime revenue and outstanding AR. Rebuild proposals to use CHOW instead")
        # Optimistic precondition. Never approve a plan based on stale CRM facts.
        for field, desired in payload.items():
            if field == "note":
                continue
            historical = acct.get(field)
            current = live.get(field)
            if str(current or "") != str(historical or "") and str(current or "") != str(desired or ""):
                raise CRMError(f"Account field {field!r} changed since proposal. Refresh/rebuild review queue before approving")
        # Keep annotations fresh if a note was changed by another reviewer.
        if kind in ("update", "duplicate", "unlisted") and "note" in payload:
            original = str(prop(acct, "note") or "")
            note_suffix = str(payload["note"])[len(original):] if str(payload["note"]).startswith(original) else "\n" + str(payload["note"])
            payload["note"] = str(prop(live, "note") or "") + note_suffix
        if all(str(live.get(k) or "") == str(v or "") for k, v in payload.items()):
            outcome = {"result": "already_applied", "account_id": aid}
        else:
            client.patch_account(aid, payload)
            outcome = {"result": "patched", "account_id": aid, "written_fields": list(payload)}

    elif kind == "new":
        target = _find_target(client, site, parent_id)
        if target:
            outcome = {"result": "existing_match_found_no_duplicate_created", "account_id": target["id"]}
        else:
            rows = client.accounts()
            sample = next((a for a in rows if prop(a, "street") and prop(a, "zip")), {})
            payload = new_account_payload(site, parent_id, sample)
            response = client.create_account(payload)
            aid = _ensure_id(response)
            if not aid:
                target = _find_target(client, site, parent_id)
                if not target:
                    raise CRMError("POST may have created account, but no id returned; investigate before retrying")
                aid = target["id"]
            outcome = {"result": "created", "account_id": aid}

    elif kind == "chow":
        old_id = str(acct["id"])
        old = client.get_account(old_id)
        if str(old.get("id")) != old_id:
            raise CRMError("Old CHOW account id mismatch")
        if str(prop(old, "parent_id") or "") == str(parent_id):
            raise CRMError("Parent already correct; stop before unnecessary CHOW creation")
        if not (money(prop(old, "lifetime_revenue")) > 0 and money(prop(old, "outstanding_ar")) > 0):
            raise CRMError("CHOW SOP no longer applies; refresh CRM and propose direct reparent")
        existing_link = prop(old, "chow_current_account")
        if existing_link:
            linked = client.get_account(existing_link)
            if str(prop(linked, "parent_id")) != str(parent_id) or not _is_same_site(site, linked):
                raise CRMError("Old account already has CHOW link to a different record; needs manual investigation")
            outcome = {"result": "already_linked", "old_account_id": old_id, "new_account_id": str(existing_link)}
        else:
            created_id = past.get("created_account_id")
            if created_id:
                target = client.get_account(created_id)
                if str(prop(target, "parent_id")) != str(parent_id) or not _is_same_site(site, target):
                    raise CRMError("Stored in-progress CHOW account fails verification; investigate")
            else:
                target = _find_target(client, site, parent_id)
                if target:
                    created_id = str(target["id"])
                else:
                    records = client.accounts()
                    sample = next((a for a in records if prop(a, "street") and prop(a, "zip")), {})
                    result = client.create_account(new_account_payload(site, parent_id, sample))
                    created_id = _ensure_id(result)
                    if not created_id:
                        target = _find_target(client, site, parent_id)
                        if not target:
                            raise CRMError("New CHOW record may exist but id missing; manually inspect before retry")
                        created_id = str(target["id"])
                # Durable checkpoint before touching the old account. Safe to retry.
                record_decision(pid, "in_progress", {"created_account_id": created_id}, path)
            # Per SOP this is THE ONLY field ever modified on the historical account.
            client.patch_account(old_id, {"chow_current_account": created_id})
            outcome = {"result": "chow_linked", "old_account_id": old_id, "new_account_id": created_id}
    else:
        raise CRMError(f"Unknown proposal kind: {kind}")
    record_decision(pid, "approved", {"outcome": outcome}, path)
    return outcome
