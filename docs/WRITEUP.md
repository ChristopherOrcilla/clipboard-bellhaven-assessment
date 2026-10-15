# Assessment writeup — fill in AFTER running and approving

## Summary
I built a reconciliation pipeline for a fictional long-term-care operator, Bellhaven Senior Living. It discovers facilities from the full paginated directory and promotions on the homepage, compares them to CRM records using geographically anchored matching, and shows differences in a human review app. Only approved decisions update the CRM through the API. A proposed daily scheduled job is read-only.

## Inputs and reliability
- Public Bellhaven directory and homepage plus location detail pages; scraper captures facility name, street, city, state, ZIP, and all listed care offerings.
- CRM sandbox accounts, including existing parent relationships, account names, status, duplicates, CHOW pointer, lifetime revenue, and outstanding AR.
- A complete scrape is required before proposing website-absence findings. At assessment time the directory displayed 34 facilities, with a homepage promotion for Findlay not in that directory. **Verify current counts again**.

## Matching methodology
Location evidence (street, ZIP, city/state) is weighted more heavily than names. Names with conflicting geography do not produce automatic matches. Name/address variants, ambiguous records, duplicates, missing facilities, stale parent IDs, inactive accounts, and website-missing CRM accounts get distinct review categories. All changes have source links, side-by-side CRM comparisons, and rationales.

## Billing history and CHOW policy
When the parent account needs correcting: if **lifetime_revenue > 0 AND outstanding_ar > 0**, I retain the old account and old parent relationship, create the new facility account under the correct parent, and link the old to the new using `chow_current_account` only. Otherwise I reparent the original. This rule is checked again at approval time, not just during the initial scan.

## Other data governance decisions
- Duplicate accounts: use `duplicate_of_account` on the losing copy, change it to `Inactive`, and explain the decision in `note`, because no merge/delete is available. Cases with billing activity receive extra review.
- Missing current website listing: change to `Needs Review` with a note rather than assume ownership ended.
- Rejected decisions are stored and excluded on future identical runs. Approved changes are reflected in CRM and normally disappear on the next scan. CHOW creates are checkpointed for safe retries.
- The daily job refreshes evidence and generates proposals but cannot change the CRM without a reviewer's separate approval.

## Results — FILL WITH ACTUAL RESULTS, NOT GUESSES
- Time invested: **[actual minutes]**
- Website facilities found: **[count]**
- CRM accounts read: **[count]**
- Proposals initially created: **[count by type]**
- Approved actions written to CRM: **[count by type]**
- Rejected for insufficient evidence: **[count]**
- Final pending review: **[count]**
- Final CRM checks: **[specific examples with before/after IDs and evidence links]**

## Tradeoffs and next steps
I preferred false-negative investigation to false-positive ownership changes. A production version could add multi-day confirmation before flagging a disappearing listing, ownership transaction feeds, change alerts, detailed CRM field mapping from a documented schema, durable shared hosted decision storage, and unit/integration tests against the official sandbox schema. This exercise intentionally keeps scheduled execution and approvals separate.
