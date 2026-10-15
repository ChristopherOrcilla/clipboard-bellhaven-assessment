# Two-minute recording outline (speak naturally; show ACTUAL changes)

0:00–0:20 — "This tool reconciles Bellhaven's current facility directory to our CRM. It crawls all three directory pages and checks the homepage for extra facilities. Matching uses addresses and ZIP codes before fuzzy names."

0:20–0:45 — Open a real proposal. Point to street/city/ZIP match, the current parent, evidence link, and projected exact write.

0:45–1:15 — "Before changing parents, the approval step checks lifetime revenue and outstanding AR. If both are positive, we preserve the old account and create a linked CHOW replacement; otherwise it can be updated directly." Approve a genuinely supported proposal.

1:15–1:35 — Show a genuinely ambiguous / insufficient-evidence proposal, explain what is missing, enter a rejection reason, click Reject. Confirm no CRM write was made by Reject.

1:35–2:00 — Open the read-only CRM account view to show the change actually landed. Point out the decided queue items are suppressed on rerun and the schedule is read-only.

**Prioritize proof of a real approved correction.** Don't invent a rejection solely for the video or approve uncertain identity matches. Hide token and `.env` in any screen capture. For a private repo, follow the assessment's instructions for code submission rather than publicly revealing a private token or workspace link.

## Live 45-minute walkthrough prep
- Know what each file does and be able to locate the write call (`bellhaven/review.py`).
- Be ready to tweak matching thresholds, add a care type, or handle a new naming variation.
- Explain why homepage-only listings matter and why name-only matching is unsafe.
- Demonstrate a safe second run: previously approved/rejected items don't come back.
- Explain failure behavior: a CHOW creation may succeed before linking; the stored new id allows retry without duplicate creation.
- Be able to explain which data can and cannot prove historical corporate ownership.
