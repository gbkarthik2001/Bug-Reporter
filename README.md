# Bug Reporter

An in-app bug catcher for Frappe / ERPNext. It works two ways at once:

- **Manual** - testers click **Report Bug** without leaving the screen where a
  problem occurred, and the app automatically fills in the technical context
  around their description.
- **Automatic** - any genuine unhandled server crash, or any uncaught
  JavaScript error in the browser, is captured and reported **with zero
  clicks**, during normal use of the site - no one has to notice a problem
  and remember to report it.

Either way, a **Bug Report** record is created with the technical context
already filled in (route, DocType/document, browser/OS, recent client-side
errors, failed requests, a best-effort correlation with server-side Error Log
entries), and the configured recipients are emailed - so consultants and
developers spend less time asking "what were you doing when this happened?",
and issues stop depending on someone remembering to report them.

Optionally, every Bug Report can also sync one-to-one with a **Redmine**
issue, including a resolution status that flows back from Redmine into
Frappe automatically.

Compatible with **Frappe / ERPNext v15 and v16**, and designed to install
cleanly alongside any other apps already on your site.

## What's included

| Area | What it does |
|---|---|
| **Bug Report** DocType | Structured record: title, description, expected/actual result, steps, severity, priority, status, auto-captured technical context, evidence |
| **Bug Reporter Settings** | Single doctype: enable/disable, allowed roles, defaults, capture toggles (manual + automatic, separately), notification recipients, dedup window, retention, optional Redmine sync |
| Report Bug button + dialog | Floating button in Desk; opens a short form with an expandable "Technical Details" section. A **Screenshot** field lets a tester manually attach an image (their own screenshot, a photo, etc.) - nothing is captured automatically |
| **Automatic server-side capture** | Any unhandled crash (HTTP 500) anywhere on the site auto-creates a Bug Report and emails the recipients - no click involved. Routine `frappe.throw()` validation/permission messages are never captured, since Frappe itself never logs those |
| **Automatic client-side capture** | Any uncaught JS error / unhandled promise rejection in the browser auto-creates a Bug Report the same way, for any logged-in user, on any page |
| Duplicate suppression | The same recurring error is only reported once per configurable time window - **scoped to the specific document it happened on**, so the same bug recurring on the same record is suppressed, but the same bug happening on a *different* record still gets its own report |
| DocType/route inference | Frappe's own crash log never records which DocType was involved - this parses it out of the captured request URL as a fallback, for both desk-form and API-call crashes |
| Client-side capture (manual flow) | Recent JS errors and failed HTTP requests, buffered passively and attached to whatever's reported next, no sensitive data |
| Error Log correlation | Best-effort match by time proximity, never blocks submission if it fails |
| Notifications | Email to configured recipients/assignee on: new report (manual or automatic), assignment, marked Resolved (to the original reporter), and a **weekly summary** of everything still open |
| Dashboard | Simple status/severity counts page, filterable list views |
| Optional Issue linkage | Reuses the standard `Issue` doctype instead of duplicating it, if present |
| **Optional Redmine sync** | Every new Bug Report (manual or automatic) also creates a matching Redmine issue, assigned to the Redmine user whose email matches the Bug Report's Assigned To. A **Sync to Redmine** button on the Bug Report lets you push later edits (assignee, description, steps to reproduce, expected/actual result) onto the same issue. A scheduled job pulls the issue's Redmine status back and marks the Bug Report Resolved once it reaches a configured status. Never blocks Bug Report creation if Redmine is unreachable or misconfigured |

## Where Severity/Priority defaults come from

**Default Severity** and **Default Priority** in Bug Reporter Settings are not
independent hardcoded values - their dropdown options are read directly from
Bug Report's own `Severity`/`Priority` fields at runtime, and whatever you
pick there is what every new Bug Report gets **unless** a human explicitly
chose a different value in the manual Report Bug dialog. Auto-captured
reports (server or client) always use the configured default - there is no
separate hardcoded severity for "auto-captured" vs. "manual" reports.

## Status workflow

Deliberately lean, four states:

```
Pending  ──────►  Resolved  ──────►  Reopened
   ▲                  │                 │
   │                  ▼                 ▼
   └───────────── Rejected ◄────────────┘
```

- **Pending** - open, default status for every new report (manual or automatic).
- **Resolved** - set by a developer/manager once fixed (or automatically, see
  below, once Redmine sync is configured). Emails the original reporter
  automatically (`Bug Reporter Settings › Notify Reporter When Resolved`).
- **Reopened** - the fix didn't hold; anyone (including the reporter) can
  set this.
- **Rejected** - won't fix / not a bug; can be moved back to Pending if
  reconsidered.

Only a **Bug Reporter Manager** (or System Manager) can mark something
Resolved or Rejected; a **Bug Reporter Tester** can open (Pending) or reopen
(Reopened) a report themselves.

## How automatic capture works (short version)

- **Server-side**: hooks into `doc_events["Error Log"]["after_insert"]`.
  Frappe only ever writes to its own core Error Log for a genuine unhandled
  exception (`http_status_code >= 500`) or an app's own explicit
  `frappe.log_error()` call - routine validation/permission errors never
  reach it, so this is "real crashes only" for free, with no monkeypatching
  of Frappe internals required.
- **Client-side**: `bug_reporter_capture.js` (loaded on every Desk page)
  installs global `window.onerror` / `unhandledrejection` listeners (plus
  `fetch`/`XMLHttpRequest` patching to also buffer failed requests). The
  moment a real error fires, it calls a whitelisted endpoint directly - no
  button, no dialog.
- Both paths share the same duplicate-suppression logic
  (`auto_capture_dedup_window_minutes` in Bug Reporter Settings), keyed on
  the error signature **plus** the specific document it happened on when one
  can be identified - so a repeat on the same record is suppressed, but the
  same underlying bug on a different record is still reported.
- A weekly scheduled job separately emails a list of everything still
  Pending/Reopened, so nothing quietly sits unnoticed between individual
  notifications.

## Redmine integration (optional)

Off by default. To enable, open **Bug Reporter Settings › Redmine Integration**:

| Field | What to put there |
|---|---|
| Sync Bug Reports to Redmine | Master on/off switch |
| Redmine URL | Base URL, e.g. `https://redmine.example.com` (no trailing slash) |
| Redmine Project Identifier | The short slug from the project's URL (Project Settings → Identifier) - not its display name |
| Redmine API Key | From Redmine → My Account → API access key. Just needs to belong to a **member of the target project** - it does not need to be a Redmine admin (see "Assignee matching" below) |
| Redmine Tracker ID | Numeric tracker ID to file issues under - check Redmine → Administration → Trackers on your instance (a stock install usually has `1` = Bug) |
| Fallback Redmine Assignee (User ID) | Used when the Bug Report's Assigned To email doesn't match any Redmine project member, or Assigned To is blank. Leave `0` to create unassigned in that case |
| Required Custom Field ID / Value | Only needed if your Redmine project has a **required custom field** on issues (distinct from Redmine's native, per-project Issue Category feature - many instances use a custom field, e.g. a billing/classification field, that's mandatory on every issue). Find the ID by opening any existing issue in that project via `{Redmine URL}/issues/<id>.json` and reading the `id` under `custom_fields` for the field with the matching name. Leave at `0` if the project has no such required field |
| Redmine Status That Marks Resolved | Checked every 15 minutes (see below) - when a synced issue's Redmine status exactly matches this name (default `Deployed to UAT`), the linked Bug Report is automatically marked Resolved here |

**Assignee matching**: the Bug Report's `Assigned To` (a Frappe User) is
resolved to that user's email, then matched against the **target project's
own member list** (not Redmine's global `/users.json` search, which requires
an admin-level key). A match's Redmine user ID becomes the issue's
`assigned_to_id`; no match falls back to the configured default, or leaves
the issue unassigned. This means the assignee's Frappe user email must match
their Redmine login exactly.

**Creating vs. updating**: the first sync happens automatically in the
background right after a Bug Report is created. After that, editing the
report (reassigning it, adding Steps to Reproduce, etc.) does **not**
auto-resync - click **Sync to Redmine** on the Bug Report form to push those
changes onto the existing issue. If a report was never synced (e.g. Redmine
was unreachable, or sync was off at the time), the same button creates the
issue instead.

**What gets sent**: only four fields flow into the Redmine issue's
description - Description, Steps to Reproduce, Expected Result, and Actual
Result - cleanly converted from Frappe's rich text to plain text. Route,
reference document, and raw error tracebacks stay in Frappe only.

**Status flowing back**: a scheduled job (every 15 minutes) checks every
Bug Report that's still Pending/Reopened and has a linked Redmine issue; if
that issue's Redmine status matches **Redmine Status That Marks Resolved**,
the Bug Report is moved to Resolved here too, with a comment explaining why.
This is one-way (Redmine → Frappe) and forward-only - it never touches a
Rejected report and never moves anything backward.

Once synced, the Bug Report shows the linked Redmine Issue ID/URL and an
**Open in Redmine** button. All Redmine calls are best-effort - a Redmine
outage or misconfiguration is logged internally but never blocks or fails
the Bug Report itself.

## Quick start

```bash
# from your bench directory
bench get-app bug_reporter /path/to/this/bug_reporter
bench --site your-site.local install-app bug_reporter
bench --site your-site.local migrate
bench build --app bug_reporter
```

Then, as an Administrator, open **Bug Reporter Settings** to configure:

- Who can submit reports manually (**Allowed Roles**), default assignee, and
  default severity/priority (options and choices come straight from Bug
  Report's own fields - see above).
- Whether automatic server-side and/or client-side capture are enabled
  (both on by default), and the duplicate-suppression window.
- **Notification Recipients** - who gets emailed for every new/auto-captured
  Bug Report, in addition to the assignee.
- Whether the reporter gets emailed when their bug is marked Resolved.
- Evidence retention (how long attachments are kept on closed reports).
- Optional Redmine sync (see above) - off by default.

## License

MIT, see `license.txt`.
