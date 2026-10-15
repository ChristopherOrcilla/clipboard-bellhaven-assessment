"""Conservative matching: location evidence dominates name; uncertain records stay for review."""
from rapidfuzz.fuzz import ratio
from .crm import prop, map_care, write_field
from .util import words, street_norm, money, key_for


def account_as_location(a):
    return {"name": prop(a, "name") or "", "street": prop(a, "street") or "", "city": prop(a, "city") or "", "state": prop(a, "state") or "", "zip": str(prop(a, "zip") or "").split("-")[0]}


def is_parent(a):
    name = words(prop(a, "name"))
    return "parent account" in name or (not prop(a, "street") and not prop(a, "city") and not prop(a, "parent_id"))


def compare(site, acct):
    old = account_as_location(acct)
    st = street_norm(site["street"])
    oldst = street_norm(old["street"])
    street_exact = bool(st and oldst and st == oldst)
    street_sim = ratio(st, oldst) if st and oldst else 0
    zip_match = bool(site["zip"] and old["zip"] and site["zip"] == old["zip"])
    city_state = words(site["city"]) == words(old["city"]) and words(site["state"]) == words(old["state"])
    name_sim = ratio(words(site["name"]), words(old["name"]))
    street_pts = 45 if street_exact else (33 if street_sim >= 93 else 0)
    score = street_pts + (25 if zip_match else 0) + (15 if city_state else 0) + 15*name_sim/100
    # Strong street/ZIP/geography or name + matching ZIP/geography.
    strong = city_state and zip_match and (street_exact or street_sim >= 93 or (name_sim >= 94 and not oldst))
    # Potential renamed/relocated property: force a human to investigate.
    name_location = city_state and name_sim >= 91
    return {"score": round(score, 2), "street_match": street_exact, "zip_match": zip_match, "city_state_match": city_state, "name_similarity": round(name_sim, 1), "strong": strong, "name_location": name_location}


def proposal(kind, site=None, account=None, changes=None, evidence=None, **extra):
    changes = changes or {}
    stable = {"kind": kind, "source_url": (site or {}).get("source_url"), "account_id": (account or {}).get("id"), "changes": changes, "survivor_id": extra.get("survivor_id")}
    return {"id": key_for(stable), "kind": kind, "facility": site or {}, "account": account or {}, "changes": changes, "evidence": evidence or {}, **extra}


def note_append(existing, new):
    existing = str(existing or "").strip()
    return (existing + "\n" if existing else "") + new


def changes_for(site, acct, parent_id):
    changes = {}
    if str(prop(acct, "parent_id") or "") != str(parent_id):
        changes["parent_id"] = parent_id
    if str(prop(acct, "status") or "") != "Active":
        changes["status"] = "Active"
    if (prop(acct, "name") or "").strip() != site["name"].strip():
        changes["name"] = site["name"]
    # Postal updates only when enough independent evidence supports identity.
    for key in ("street", "city", "state", "zip"):
        a = prop(acct, key)
        s = site[key]
        if (not a or (key == "street" and street_norm(a) != street_norm(s)) or (key != "street" and words(a) != words(s))):
            changes[write_field(acct, key)] = s
    # Avoid overwriting a valid care subtype when the website has multiple offerings.
    mapped = map_care(site.get("care_offerings"))
    listed_cares = {map_care([o]) for o in site.get("care_offerings", [])}
    if mapped and (not prop(acct, "care_type") or (len(listed_cares) == 1 and prop(acct, "care_type") not in listed_cares)):
        changes["care_type"] = mapped
    return changes


def reconciliation(facilities, accounts):
    if len(facilities) < 30:
        raise ValueError("Website scrape incomplete (fewer than 30), refusing reconciliation")
    parents = [a for a in accounts if "bellhaven senior living" in words(prop(a, "name")) and is_parent(a)]
    if len(parents) != 1:
        raise ValueError(f"Expected exactly one Bellhaven parent account, found {len(parents)}; inspect CRM before changes")
    parent_id = str(parents[0]["id"])
    regular_accounts = [a for a in accounts if not is_parent(a) and not prop(a, "duplicate_of_account") and not prop(a, "chow_current_account")]
    proposals = []
    seen_existing = set()
    matched = []
    confirmed = []
    site_urls = set()

    for site in facilities:
        if site["source_url"] in site_urls:
            raise ValueError("Duplicate website source URL: incomplete or faulty scrape")
        site_urls.add(site["source_url"])
        scored = sorted(((compare(site, a), a) for a in regular_accounts), key=lambda pair: pair[0]["score"], reverse=True)
        strong = [(sc, a) for sc, a in scored if sc["strong"]]
        suspicious = [(sc, a) for sc, a in scored if sc["name_location"]]
        if not strong:
            if suspicious:
                sc, a = suspicious[0]
                seen_existing.add(str(a["id"]))
                proposals.append(proposal("investigate", site, a, evidence={"reason": "Same/similar name and town, but address or ZIP disagrees. Do not create a possibly duplicated account.", "score_details": sc, "source_url": site["source_url"]}, risk="High"))
            else:
                proposals.append(proposal("new", site, evidence={"reason": "No sufficiently supported account match across full CRM", "best_candidate": {"name": prop(scored[0][1], "name"), "score": scored[0][0]["score"]} if scored else None, "source_url": site["source_url"]}, risk="Medium"))
            continue

        # Two very strong candidates at same street/ZIP strongly suggest a duplicate.
        def survivor_rank(pair):
            sc, a = pair
            return (money(prop(a, "outstanding_ar")) > 0, money(prop(a, "lifetime_revenue")) > 0, sc["score"], str(prop(a, "status")) == "Active")
        strong.sort(key=survivor_rank, reverse=True)
        sc, winner = strong[0]
        seen_existing.add(str(winner["id"]))
        matched.append((site, winner))
        # Some locations could genuinely have two programs at one street; name evidence is required for duplicate proposal.
        for losesc, loser in strong[1:]:
            if str(loser["id"]) == str(winner["id"]):
                continue
            if losesc["name_similarity"] < 79:
                # Separate business at same address: do not merge based on address alone.
                continue
            seen_existing.add(str(loser["id"]))
            financial = (money(prop(loser, "outstanding_ar")) > 0 or money(prop(loser, "lifetime_revenue")) > 0)
            changes = {"duplicate_of_account": winner["id"], "status": "Inactive", "note": note_append(prop(loser, "note"), f"Bellhaven reconciliation: probable duplicate of account {winner['id']}. Site evidence {site['source_url']}. Preserve historical billing records; no merge or deletion.")}
            proposals.append(proposal("duplicate", site, loser, changes, {"reason": "Same postal address, location, and highly similar business name", "score_details": losesc, "survivor": winner["id"], "source_url": site["source_url"]}, survivor_id=winner["id"], risk="High" if financial else "Medium"))

        modifications = changes_for(site, winner, parent_id)
        if "parent_id" in modifications and money(prop(winner, "lifetime_revenue")) > 0 and money(prop(winner, "outstanding_ar")) > 0:
            # Mandatory CHOW: no name, parent, status, notes or other changes to old account.
            proposals.append(proposal("chow", site, winner, {"new_parent_id": parent_id}, {"reason": "Parent correction requires a new account because both revenue history and outstanding AR are positive", "lifetime_revenue": str(prop(winner, "lifetime_revenue")), "outstanding_ar": str(prop(winner, "outstanding_ar")), "score_details": sc, "source_url": site["source_url"]}, risk="Critical"))
        elif modifications:
            modifications["note"] = note_append(prop(winner, "note"), f"Bellhaven reconciliation from verified current listing: {site['source_url']}. Care offerings: {', '.join(site.get('care_offerings', []))}.")
            proposals.append(proposal("update", site, winner, modifications, {"reason": "High-confidence identity; CRM fields differ from site or parent", "score_details": sc, "source_url": site["source_url"]}, risk="High" if "parent_id" in modifications else "Low"))
        else:
            confirmed.append({"site": site["name"], "account_id": winner["id"]})

    # Extra Bellhaven children may have sold, closed, rebranded, or disappeared temporarily.
    # Never infer a completed sale merely because a listing disappeared.
    for a in accounts:
        aid = str(a.get("id", ""))
        if is_parent(a) or aid in seen_existing or prop(a, "duplicate_of_account") or prop(a, "chow_current_account"):
            continue
        if str(prop(a, "parent_id") or "") == parent_id:
            if str(prop(a, "status")) == "Needs Review":
                continue
            change = {"status": "Needs Review", "note": note_append(prop(a, "note"), "Bellhaven reconciliation: facility not located on current directory or homepage. Investigate sale, closure, renaming, and historical ownership; not proof of divestiture.")}
            proposals.append(proposal("unlisted", account=a, changes=change, evidence={"reason": "CRM says Bellhaven-owned but no current website listing supports that; do not automatically unlink or mark inactive."}, risk="Medium"))

    # Guard against one CRM account mapped to more than one distinct website facility.
    mapped_ids = {}
    for site, account in matched:
        mapped_ids.setdefault(str(account["id"]), []).append(site["name"])
    conflicts = {aid: names for aid, names in mapped_ids.items() if len(names) > 1}
    if conflicts:
        # Stop entirely rather than output a contradictory review queue.
        raise ValueError(f"Website facilities map to the same CRM account: {conflicts}. Resolve ambiguity first")
    return {"parent_id": parent_id, "proposals": proposals, "confirmed": confirmed, "counts": {"facilities": len(facilities), "crm_accounts": len(accounts), "confirmed_no_change": len(confirmed), "proposals_total": len(proposals)}}
