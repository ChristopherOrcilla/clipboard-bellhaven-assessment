"""Streamlit CRM reconciliation reviewer. CRM mutations require an explicit click."""
import json
import os
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv
from bellhaven.crm import CRMClient, CRMError, prop
from bellhaven.pipeline import refresh, latest
from bellhaven.review import approve, reject, decisions
from bellhaven.util import money

load_dotenv()
st.set_page_config(page_title="Bellhaven · Ownership Review", page_icon="🏢", layout="wide")
st.title("Bellhaven · CRM ownership reconciliation")
st.caption("Evidence-first review. The website scan and proposal creation are read-only. No CRM record changes without an explicit approval.")

if "auth_token" not in st.session_state:
    st.session_state.auth_token = os.getenv("CRM_TOKEN", "")
with st.sidebar:
    st.header("Connection")
    st.session_state.auth_token = st.text_input("CRM API token (never displayed in exports)", value=st.session_state.auth_token, type="password")
    st.caption("Or store the token only in your local .env file. Never upload .env to GitHub or show it in the demo.")
    st.caption("API authentication and endpoint settings live in .env. Confirm them against /api/docs before approving anything.")
    client = CRMClient(token=st.session_state.auth_token)
    if st.button("Test CRM connection", use_container_width=True):
        try:
            records = client.accounts()
            st.success(f"Read {len(records)} account records")
            if len(records) < 100:
                st.warning("Expected around 120 accounts. Verify pagination before trusting reconciliation")
        except Exception as e:
            st.error(str(e))
    st.divider()
    if st.button("Refresh website + CRM (read only)", type="primary", use_container_width=True):
        try:
            with st.spinner("Discovering website locations; reading every CRM page; making proposals..."):
                bundle = refresh(client)
            st.success(f"Scan complete: {bundle['counts']['pending_review']} pending proposals")
            st.rerun()
        except Exception as e:
            st.error(str(e))
    st.caption("Refresh may take several requests. It does not send POST, PATCH, PUT, or DELETE.")
    st.divider()
    st.caption("Switching computers? Commit and push state/decisions.json to your PRIVATE repo at the end of each session, then pull it before starting on the other computer.")

bundle = latest()
if not bundle:
    st.info("First, configure your private token in .env, test the connection, then click **Refresh website + CRM (read only)** in the sidebar.")
    st.markdown("**Assessment SOP:** If both lifetime revenue and outstanding AR exceed zero and a facility must move parents, create a new account under the correct parent. Link the old record through `chow_current_account`. Do not modify the old parent or any of its other fields.")
    st.stop()

counts = bundle.get("counts", {})
a, b, c, d = st.columns(4)
a.metric("Facilities discovered", counts.get("facilities", 0))
b.metric("CRM accounts scanned", counts.get("crm_accounts", 0))
c.metric("No-change confirmations", counts.get("confirmed_no_change", 0))
d.metric("Proposals at scan", counts.get("pending_review", 0))
st.caption(f"Last read-only refresh: {bundle.get('refreshed_at', 'unknown')} | Website: {bundle.get('website_stats', {})}")

all_proposals = bundle.get("proposals", [])
dec = decisions()
open_props = [p for p in all_proposals if dec.get(p["id"], {}).get("status") not in ("approved", "rejected")]
# Display critical financial exceptions first, then parent changes, duplicates, and routine fixes.
kind_priority = {"chow": 0, "duplicate": 1, "update": 2, "new": 3, "investigate": 4, "unlisted": 5}
open_props.sort(key=lambda p: (kind_priority.get(p["kind"], 99), -({"Critical": 4, "High": 3, "Medium": 2, "Low": 1}.get(p.get("risk"), 0))))
tab1, tab2, tab3 = st.tabs([f"Review queue ({len(open_props)})", "Decisions & audit trail", "How decisions work"])
with tab1:
    if not open_props:
        st.success("No undecided proposals from the latest scan. Refresh to reconcile against live CRM again.")
    else:
        names = lambda p: f"{p['kind'].upper():11} · {p.get('facility', {}).get('name') or p.get('account', {}).get('name', 'Unknown')} · {p.get('risk', '?')} · {p['id'][:7]}"
        kinds = ["All"] + sorted({p["kind"] for p in open_props})
        chosen_kind = st.selectbox("Filter action type", kinds)
        filtered = [p for p in open_props if chosen_kind == "All" or p["kind"] == chosen_kind]
        choices = {names(p): p for p in filtered}
        if not choices:
            st.info("No pending proposals in that category.")
        else:
            label = st.selectbox("Select a proposal", list(choices))
            p = choices[label]
            acct = p.get("account") or {}
            site = p.get("facility") or {}
            evidence = p.get("evidence") or {}
            st.subheader(site.get("name") or acct.get("name") or "Account")
            st.markdown(f"**Proposed action:** `{p['kind']}` · **Risk:** `{p.get('risk')}` · **Decision key:** `{p['id']}`")
            st.write(evidence.get("reason", ""))
            left, right = st.columns(2)
            with left:
                st.markdown("#### Website evidence")
                if site:
                    st.write("**Location:**", f"{site.get('street','')}, {site.get('city','')}, {site.get('state','')} {site.get('zip','')}")
                    st.write("**Care offerings:**", ", ".join(site.get("care_offerings", [])))
                    if site.get("source_url"):
                        st.link_button("Open original facility page", site["source_url"])
                else:
                    st.write("No listing was found in the completed current website crawl. **This does not establish sale or closure.**")
            with right:
                st.markdown("#### Existing CRM evidence")
                if acct:
                    st.write("**ID:**", acct.get("id"))
                    st.write("**Name:**", prop(acct, "name"))
                    st.write("**Current parent ID:**", prop(acct, "parent_id"))
                    st.write("**Status:**", prop(acct, "status"))
                    st.write("**CRM location:**", f"{prop(acct, 'street')}, {prop(acct, 'city')}, {prop(acct, 'state')} {prop(acct, 'zip')}")
                    st.write("**Lifetime revenue:**", prop(acct, "lifetime_revenue"))
                    st.write("**Outstanding AR:**", prop(acct, "outstanding_ar"))
                    browser = os.getenv("CRM_BROWSER_URL", "").rstrip("/")
                    if browser:
                        st.link_button("Open account in read-only CRM", f"{browser}/{acct['id']}")
                else:
                    st.write("No supported existing CRM account found")
            if evidence.get("score_details"):
                st.markdown("#### Matching evidence")
                st.json(evidence["score_details"], expanded=False)
            st.markdown("#### Exact proposed write")
            if p["kind"] == "chow":
                st.warning("**MANDATORY CHOW SOP:** Create a NEW facility account under Bellhaven. Preserve the historical account's current parent, name, status, revenue, AR, and notes. Update ONLY its `chow_current_account` field to point to the new record. A partial failure can be resumed.")
                st.json({"step_1": "Create account under Bellhaven", "step_2": "PATCH old account chow_current_account to new id", "old_account_parent_changed": False})
            elif p["kind"] == "new":
                st.write("Create a new Active facility account under Bellhaven, populated from the website's published address and care offerings. Recheck for an existing account immediately before creating.")
            elif p["kind"] == "investigate":
                st.warning("Conflicting identity evidence: mark the EXISTING CRM record Needs Review with a note; do not change its parent or create a replacement.")
            else:
                st.json(p.get("changes", {}), expanded=True)
            if p["kind"] == "duplicate" and (money(prop(acct, "outstanding_ar")) > 0 or money(prop(acct, "lifetime_revenue")) > 0):
                st.error("Financial activity exists on the possible duplicate. Confirm the selected surviving record and preservation of historical billing before inactivation.")
            if p["kind"] == "unlisted":
                st.warning("A missing website listing alone is not proof of sale or closure. Proposed status is **Needs Review**, not Inactive or reparented.")

            st.divider()
            ack = st.checkbox("I reviewed the actual website evidence, current CRM details, financial SOP, and proposed fields.", key="ack_" + p["id"])
            colapprove, colreject = st.columns(2)
            with colapprove:
                if st.button("Approve and WRITE TO CRM", type="primary", disabled=not ack, use_container_width=True):
                    try:
                        outcome = approve(p, client, bundle["parent_id"])
                        st.success(f"Approved: {outcome}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Nothing marked approved. Review error: {exc}")
            with colreject:
                reason = st.text_input("Reason to reject", key="why_" + p["id"], placeholder="e.g. address conflict; insufficient evidence")
                if st.button("Reject (NO CRM WRITE)", disabled=not reason.strip(), use_container_width=True):
                    try:
                        reject(p, reason)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
with tab2:
    hist = decisions()
    if hist:
        st.dataframe([{"proposal_id": k, "status": v.get("status"), "date": v.get("at"), "rationale": v.get("rationale", ""), "outcome": json.dumps(v.get("outcome", {}))} for k, v in hist.items()], use_container_width=True, hide_index=True)
        st.download_button("Download decisions JSON", json.dumps(hist, indent=2), "decisions.json", mime="application/json")
    else:
        st.write("No decisions recorded yet. Rejections and approvals will appear here.")
    st.caption("Decision keys remain stable across identical runs. Commit/push state/decisions.json privately to share decisions between computers.")
with tab3:
    st.markdown("""
**Matching hierarchy:** street + ZIP + city/state first; names provide supporting evidence. Name-only matches in conflicting locations do **not** authorize a change.

**CHOW policy:** positive lifetime revenue **and** positive outstanding AR + required parent change => create new account, then link old via `chow_current_account` only. Otherwise reparent the existing account.

**Duplicates:** a reviewer chooses the surviving account; the losing account is marked Inactive and pointed at the survivor with `duplicate_of_account`. No merge or deletion. Financial duplicates require extra caution.

**Unlisted:** a listing disappearing could mean divestiture, closure, outage, or rebranding. Mark Needs Review rather than assume former ownership.

**Reruns:** approvals and rejections are stored by a deterministic proposal ID. Approved CRM updates disappear from future differences; rejected same proposals are suppressed. CHOW uses a checkpoint so partial writes are resumable.

**Daily:** `python daily.py` and the included scheduled GitHub Action generate proposals only. They never approve or change CRM accounts.
""")
