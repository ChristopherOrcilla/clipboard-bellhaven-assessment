# Bellhaven Senior Living — CRM Reconciliation

A human-in-the-loop, evidence-backed pipeline for the Clipboard Health analyst assessment.

**What it does:** Crawls every paginated Bellhaven community listing *plus homepage-only promotions*, compares facilities against all CRM accounts, generates auditable ownership and cleanup proposals, enforces CHOW billing protection, and provides a Streamlit reviewer who must explicitly approve any CRM writes. A daily GitHub Actions workflow is read-only.

> IMPORTANT: The live Swagger UI at `/api/docs` uses JavaScript and could not be independently parsed in this package's build environment. The default `/accounts`, `GET`, `POST`, `PATCH`, and `Authorization: Bearer` settings are **unverified assumptions**, not confirmed API facts. Before approving, check the actual docs and edit `.env` or `bellhaven/crm.py` as appropriate. The project intentionally fails rather than pretending to work if the response schema differs. Also verify the exact create/update field names, especially postal code.

## Step 1 — Prepare the computer

Python 3.11 or later, internet, and a current browser are all you need. Mac and Windows are supported. **No paid AI API is needed.**

1. Extract the ZIP to a folder named `clipboard_bellhaven_assessment`.
2. Create a local `.env` by copying `.env.example`.
3. Paste your *private* assessment token into `CRM_TOKEN` in `.env`. Do **not** paste it into chat, GitHub, the screen recording, or a screenshot.
4. Open the provided [interactive API docs](https://analyst-assessment-production.up.railway.app/api/docs). Confirm:
   - Authentication header: `Authorization: Bearer`, `X-API-Key`, or another documented format. Set `CRM_AUTH_STYLE` accordingly.
   - List-account route and pagination: default `GET /api/v1/accounts`. Set `CRM_ACCOUNTS_PATH` if different.
   - Account detail route, create route, and update route/method. Defaults are `GET /accounts/{id}`, `POST /accounts`, `PATCH /accounts/{id}`. Customize `bellhaven/crm.py` if docs say differently.
   - The read/write field names: `name`, `parent_id`, `status`, `note`, `duplicate_of_account`, `chow_current_account`, `lifetime_revenue`, `outstanding_ar`, `billing_street`, `billing_city`, `billing_state`, and ZIP key (`billing_postal_code` or `billing_zip`). Update `CRM_ZIP_WRITE_FIELD` as necessary.
   - If your API uses a required request envelope (for example `{"account": {...}}`), customize `CRMClient.patch_account` and `create_account` before approving.
5. Add your private CRM browser URL from the assessment to `CRM_BROWSER_URL` **locally only** so the UI can open account details. It is optional.

**Mac:** open Terminal in the project folder and run:

```bash
bash run_mac.sh
```

**Windows PowerShell:** open PowerShell in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

A browser usually opens at `http://localhost:8501`.

## Step 2 — Confirm READ-ONLY access first

Click **Test CRM connection**. It should fetch approximately **121 accounts** in your sandbox, not just one page of results. If it fails, verify API docs/authentication. **Do not approve a change until the correct complete list loads.**

Then click **Refresh website + CRM (read only)**. Inspect the website total. The directory currently advertises 34 communities across 3 pages, while the homepage promotes Findlay separately, bringing the expected total to about 35. A number unexpectedly below 30 will block the scan and prevent inaccurate mass "unlisted" findings.

You can inspect every proposal's website source link, location, CRM record details, matching evidence, planned write payload, parent, and billing history.

## Step 3 — Review and actually correct the CRM

Click the approval acknowledgement for a specific proposal, then **Approve and WRITE TO CRM**. This is the **only app route** that can call POST/PATCH. Review the resulting CRM account in the browser and verify the change. Enter a reason and click **Reject** for proposals that are unsupported; rejection never writes to the CRM.

**Do not approve all blindly.** Focus first on ownership defects, missing facilities, verified duplicates, CHOW exceptions, and then other safe corrections. If an account may be a duplicate but has active financial history, pause and check which one should survive.

Perform a fresh read-only refresh after several approvals and again before submission. Verify that approved changes persist, rejected findings do not reappear, and the parent facility list reflects your final decisions.

## Step 4 — Work on BOTH computers (recommended: private GitHub repo)

Use GitHub as your private code and *decisions* synchronization mechanism. Never synchronize the private token through Git.

**Computer A:**

```bash
git init
git add .
git commit -m "Initial Bellhaven reconciliation app"
git branch -M main
# Create a PRIVATE empty repository on github.com, then:
git remote add origin https://github.com/YOUR_USER/YOUR_PRIVATE_REPO.git
git push -u origin main
```

**Computer B:**

```bash
git clone https://github.com/YOUR_USER/YOUR_PRIVATE_REPO.git
cd YOUR_PRIVATE_REPO
# Copy .env.example to .env on THIS computer and enter your token locally.
# Start with the Mac/Windows command above.
```

**Each time you switch computers:**

1. At the end of a review session, run `git add state/decisions.json && git commit -m "Record review decisions" && git push` on the current device. Include changes to the code in the commit if needed.
2. On the other device, run `git pull` *before* opening the app. Then click **Refresh website + CRM (read only)** to regenerate the latest proposal queue using both the up-to-date CRM and shared review decisions.
3. Do **not** review simultaneously on both computers. If the last CHOW approval is `in_progress`, switch devices only after safely completing the linked write and syncing state.

The `data/` directory holds regenerable snapshots, so it is intentionally not committed. `.env` is also ignored. `state/decisions.json` **is tracked** so approved/rejected proposal IDs persist between computers.

## Step 5 — Validate and present

Run tests:

```bash
python -m pytest -q
```

Create your short video while actually working the queue: open evidence, approve one real supported change, reject one genuinely unsupported or ambiguous suggestion, and show the approved change in the CRM browser. Do not display tokens in the recording. See `docs/DEMO_SCRIPT.md` and `docs/WRITEUP.md`.

The final submission needs **the corrected CRM state**, **a short demo link with Anyone with link → Viewer**, **your code/repository link or files as requested**, and **your honest time spent**.

## Matching/decision design

- Strong positive evidence: standardized street address, 5-digit ZIP, city and state. Name similarity adds evidence but never overrides a contradictory geography.
- Same name and town but different street/ZIP: `investigate` / Needs Review rather than create a new potentially duplicate record.
- Parent mismatch: normally update `parent_id` directly; **if lifetime revenue > 0 AND outstanding AR > 0, never reparent the old account**. Create a new account and set only old `chow_current_account` to the new ID.
- Duplicate: choose a survivor, set `duplicate_of_account` and `Inactive` on the losing account. No merge/delete possible. Flag financial copies as high risk.
- Website-only: propose a new account, but check again immediately before creating.
- CRM-only Bellhaven child: `Needs Review` and explanatory note; absence is not proof of divestiture.
- Matched record's name, address, status, or care subtype differs: propose a cautious fix; never replace an existing care type if it remains a valid option in a multi-offering website list.
- Idempotency: stable proposal hashes and tracked `state/decisions.json` suppress previously approved/rejected proposals. Reads of the live CRM detect already-applied changes. CHOW write is retriable after a partial failure.
- Safety: scan is halted if the page count is suspicious, the corporate parent is ambiguous, or one CRM account matches multiple separate site records.

## Limitations / manual review triggers

This is a deliberately conservative assessment-sized solution. It does not use geocoding, external government ownership filings, transaction records, or legal corporate registries. The Bellhaven website establishes its *current advertised network*, not a legally authoritative historical date of sale. Two separate facilities may share a campus address; duplicate proposals should be checked for differences in name/program and financial records. Parent company IDs must be verified against the actual CRM schema. If there is an API error after a POST, inspect the CRM before manually retrying.

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
