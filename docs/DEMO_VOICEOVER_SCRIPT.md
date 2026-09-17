# Bug Reporter — Full Narration Script (for ElevenLabs / TTS)

Each **PART** below is clean, continuous narration text — safe to copy-paste
directly into ElevenLabs with nothing extra to strip out. A compact
**Screen Guide** is included at the very end, mapping each part to what to
have open on screen while that part plays — keep that separate from what
you paste into the TTS tool.

Total narration is long-form and detailed by design. Rough spoken runtime
at a natural pace: **16–20 minutes**.

---

## PART 1 — What is Bug Reporter?

Bug Reporter is an application built for Frappe and ERPNext. Its job is
simple to describe but genuinely useful in practice: it catches bugs the
moment they happen, and it makes sure whoever has to fix that bug gets
enough detail to actually do it, without a back-and-forth conversation
first.

Here's the problem it solves. In any real system, users run into errors
all the time — a form won't save, a button throws an error, a background
process crashes. Most of those errors never get reported at all, because
reporting a bug is extra work, and people are busy. And the ones that do
get reported usually arrive as a one-line message like "it's not working",
with no detail about what page it was, what the user was doing, or what
the system actually said when it failed. A developer then has to spend
time just trying to reproduce the problem before they can even start
fixing it.

Bug Reporter closes that gap in two ways at the same time.

The first way is manual. Any user who's allowed to can click a small
"Report Bug" button that floats on every screen, describe what went wrong
in their own words, and submit it — without leaving the page they were on.

The second way is fully automatic, and this is where the real value is.
Any genuine crash on the server, or any error that happens silently in the
user's browser, is captured on its own — with zero clicks from anyone.
Nobody has to notice the problem. Nobody has to remember to report it.
Nobody has to know how to describe it technically. The system does that
part itself.

Either way — manual or automatic — what comes out the other end is the
same: a structured Bug Report record, with the technical detail already
filled in. Which page it happened on. Which document was involved, if any.
What the browser and operating system were. The exact error message or
full crash traceback. Any other errors or failed requests that happened
around the same time. All of that is captured automatically, so the person
fixing the bug isn't starting from nothing.

Now, the advantages, stated plainly.

First: nothing gets missed. Because real crashes are captured automatically,
a bug doesn't depend on a human being motivated enough to report it.

Second: reports arrive with the context already attached, which means far
less time spent asking "what were you doing when this happened", and far
more time spent actually fixing the problem.

Third: it doesn't create noise. If the same underlying bug happens ten
times in a row — say, a bulk import that fails on eight records with the
identical error — Bug Reporter is smart enough to create exactly one ticket
for that one bug, not eight. But if a genuinely different problem shows up,
even seconds later, that gets its own ticket. So the inbox stays useful
instead of flooded.

Fourth: it keeps people in the loop automatically. The right people get
emailed the moment a new bug appears, the reporter gets emailed the moment
their bug is fixed, and once a week, anyone who needs to know gets a
summary of everything that's still open.

Fifth: it's optional to extend. If your team already tracks work in
Redmine, Bug Reporter can mirror every bug into a matching Redmine issue
automatically, and even bring the resolution status back the other way,
without anyone updating two systems by hand.

And finally: everything about how it behaves — who can report bugs, what
counts as duplicate, who gets notified, whether Redmine sync is even on —
is controlled from one settings screen. No code changes needed to adjust
any of it.

---

## PART 2 — How to Use It

Let's walk through actually using the app, starting with the manual side,
since that's the one a person directly interacts with.

Anywhere in the system where you have permission to report a bug, you'll
see a small floating button labeled Report Bug. Clicking it opens a short
form. You give it a title and a description of the problem — those two
are required, everything else is optional. If you know what you expected
to happen versus what actually happened, there are separate fields for
that too. There's also a Steps to Reproduce field, so if you know exactly
how to trigger the problem again, you can write that down for whoever
picks it up.

You'll also see Severity and Priority already filled in with sensible
defaults — someone configured those centrally, so you don't have to guess
what the "normal" level should be, though you're free to change them if
this particular bug really is more urgent or more severe than usual.

There's a Screenshot field too, and this one is entirely manual — if
attaching an image would help explain the problem, you attach it yourself,
the same way you'd attach a file to any email.

One more thing worth knowing about the manual dialog: it automatically
shows you an expandable "Technical Details" section, already populated
with any recent JavaScript errors or failed requests the system happened
to notice in the background while you were using the page. You don't have
to do anything to get that — it's just there, ready, if it's relevant.

Once you click Submit, that's it — the bug is filed, and you'll see a
confirmation with its ID.

Now, the automatic side needs no action from a user at all, which is
exactly the point. If something crashes on the server — a genuine
unhandled error, not just a normal validation message — a Bug Report is
created in the background instantly, with the full crash detail attached.
If a JavaScript error happens in someone's browser while they're using the
site, the same thing happens there too. In both cases, nobody clicked
anything. The system simply noticed, and reported it.

From there, whether a report was manual or automatic, it behaves the same
way: someone with the right permission works it, moves it through its
status, and the people who need to know are kept in the loop by email
automatically. We'll go through exactly how that status flow and those
emails work a little later in this walkthrough.

---

## PART 3 — Bug Reporter Settings, field by field

Everything about how Bug Reporter behaves is controlled from a single
settings screen, called Bug Reporter Settings. Let's go through it
section by section.

At the very top is **Enable Report Bug Button**. This is the master switch
for the manual button — turn it off, and the floating button disappears
from every page, site-wide.

Right next to it is **Automatically Create Linked Issue**. If your site
also uses Frappe's standard Issue doctype for tracking work, turning this
on will create a matching Issue automatically alongside every Bug Report,
so it shows up wherever your team already tracks Issues too.

Next is the **Access** section. **Allowed Roles** is a table where you list
which roles are permitted to submit a bug report manually — leave it
empty, and it defaults sensibly to Bug Reporter Tester, Bug Reporter
Manager, and System Manager. **Default Assignee** is simply who a new bug
report gets assigned to out of the box. And then there's **Default
Severity** and **Default Priority** — worth calling out specifically,
because these aren't arbitrary hardcoded choices. Their available options
are read directly from the Bug Report record's own Severity and Priority
fields, so the two can never drift out of sync with each other, and
whichever value you pick here is what every new report gets — both
automatic ones, and manual ones where the person reporting didn't
deliberately choose something else.

Moving to the **Capture** section: **Enable Client-side Error Capture**
controls whether that "Technical Details" preview — recent errors and
failed requests — shows up in the manual dialog. **Enable Error Log
Association** turns on a best-effort matching feature: when a bug is
reported, the system looks for a server-side crash log entry that happened
around the same time, and links it in automatically, in case it's related.
**Error Log Correlation Window** is simply how many minutes back it's
allowed to look while doing that matching.

Then comes the section that does the real automatic work: **Automatic
Capture, no click required**. **Auto-capture Unhandled Server Errors** is
the master switch for catching real server crashes on its own. **Auto-
capture Browser Console Errors** is the equivalent switch for catching
uncaught JavaScript errors in the browser. And **Duplicate Suppression
Window** controls how many minutes have to pass before the exact same
recurring error is allowed to create a new report again — this is exactly
the setting that stops one flaky process from flooding the system with
identical tickets, while still letting a genuinely new problem through
immediately.

Under **Attachments**, there's **Evidence Retention**, in days. This
controls a cleanup job that removes attached files — screenshots and so
on — from bug reports that have already been closed, once they've been
closed for longer than this many days. Leave it at zero, and evidence is
kept forever.

The **Notifications** section has **Notification Recipients**, a simple
list of people who should be emailed whenever a new bug report comes in,
in addition to whoever it's assigned to. And **Notify Reporter When
Resolved** — when this is on, the person who originally reported a bug
gets an email the moment it's marked Resolved, so they know their issue
was actually addressed.

And finally, **Redmine Integration** — which is significant enough that
it gets its own full section next.

---

## PART 4 — Redmine Integration, explained and shown

Redmine integration is entirely optional, and it's off by default. Let's
open it and go through every field, because there are a few details here
that genuinely matter for getting it working correctly.

The first field is **Sync Bug Reports to Redmine** — the master on/off
switch for the whole feature. Nothing else in this section does anything
until this is checked.

**Redmine URL** is simply the base web address of your Redmine instance.
**Redmine Project Identifier** is the short slug from that project's own
URL — not its display name, the actual identifier text you'd see in the
address bar when you're inside that project in Redmine.

**Redmine API Key** comes from your own Redmine account, under My Account,
API access key. Here's an important detail: this key only needs to belong
to an ordinary member of the target project — it does not need to be an
administrator account. That matters because Redmine normally restricts
searching its full user list to admins only, and Bug Reporter is built to
avoid needing that kind of access at all. Instead, it matches an assignee
by looking at the project's own member list directly and comparing email
addresses — so as long as the Frappe user's email matches their Redmine
login exactly, assignment works correctly with a completely ordinary
project-member key.

**Redmine Tracker ID** is the numeric ID of the tracker new issues should
be filed under in Redmine — on a typical instance, that's usually the
number one, corresponding to the Bug tracker, but you can check your own
instance's Administration settings to confirm.

**Fallback Redmine Assignee** is a numeric Redmine user ID used only when
the Bug Report's assignee doesn't match anyone in the project, or when
there's no assignee at all. Leave it at zero, and in that situation the
issue is simply created unassigned instead.

Now, two fields that exist specifically because of something worth
explaining. **Required Custom Field ID** and **Required Custom Field
Value**. Some Redmine projects have a custom field that's mandatory on
every single issue — often something like a billing or work classification
field — completely separate from Redmine's own built-in Issue Category
feature. If your project has one of those mandatory custom fields, these
two settings let you tell Bug Reporter exactly which field, by its numeric
ID, and exactly what value to send for it, so syncing doesn't fail with an
error about a required field being blank. If your project doesn't have
anything like that, you can simply leave these at zero.

And the last field, **Redmine Status That Marks Resolved**. This is where
the integration becomes genuinely two-way. A background job checks, every
fifteen minutes, every Bug Report that's still open and has a linked
Redmine issue. If that issue's current status in Redmine exactly matches
whatever you've typed here — by default, "Deployed to UAT" — the Bug
Report here is automatically moved to Resolved, with a note explaining
exactly why. So once a fix reaches that stage in Redmine, nobody has to
remember to also go update the record over here.

A quick word on how the day-to-day sync actually behaves. The first time a
Bug Report is created, it's synced into Redmine automatically in the
background — no button needed. If you edit that report afterward — say,
you reassign it, or add steps to reproduce — that edit does not
automatically push to Redmine on its own. Instead, there's a "Sync to
Redmine" button right on the Bug Report itself, and clicking it pushes
those changes onto the existing issue. If, for whatever reason, a report
was never synced in the first place — Redmine happened to be unreachable
at the time, say — that same button will create the issue instead. And
once something is synced, you'll also see an "Open in Redmine" button that
takes you straight to the live issue.

One last detail worth knowing: only four fields are actually sent into the
Redmine issue's description — the Description, Steps to Reproduce,
Expected Result, and Actual Result. Route information, linked documents,
and raw crash tracebacks intentionally stay in Frappe only, and aren't
pushed across.

---

## PART 5 — The Bug Report doctype, field by field

Now let's look at the actual record itself — the Bug Report — and go
through what every field is for.

**Title** and **Status** sit right at the top — Status moves through
Pending, Resolved, Reopened, or Rejected, and it's required on every
record. Right beside it are **Severity** and **Priority** — Severity
ranges from Critical down to Low, Priority from Urgent down to Low, and
both are required.

**Reported By** and **Reported At** are stamped automatically the moment a
report is created — always from the real session and the real time,
regardless of what any script or automated process might try to send in,
so these two fields can always be trusted. **Auto-captured** is a simple
checkbox that's ticked whenever the report came from one of the automatic
capture paths rather than a human filling in the manual dialog. **Assigned
To** is who's currently responsible for it, and changing this field is
what triggers an assignment notification email.

Then there's the **Details** section. **Description** is the main
free-text explanation, required on every report. **Expected Result** and
**Actual Result** are optional plain-text fields for exactly what they
sound like. **Steps to Reproduce** lets someone lay out, step by step,
exactly how to make the problem happen again.

Under **Evidence**, there's the **Screenshot** field — a plain, manual
image attachment, entirely at the reporter's discretion.

The **Technical Details** section is where the automatically-captured
context lives. **Route** is the page or API path where the problem
happened. **DocType** and **Document Name** identify the specific record
involved, when one can be identified. **Company**, **Browser**, and
**Operating System** describe the environment. **Correlation ID** is an
internal signature used behind the scenes for duplicate detection — not
something you'd normally need to read yourself, but it's there.

The **Error Capture** section holds **Error Message**, a short version of
what went wrong, and **Related Error Log**, a link to the matching entry
in Frappe's own core crash log, when one was found. **Client-side Errors**
and **Failed Requests** are stored as raw technical detail — a small log
of what else was going wrong in the browser around the same time. And
**Installed Apps** simply records which apps were installed on the site
at the time, useful context for reproducing an environment-specific issue.

Under **Resolution**, there are two free-text fields for whoever fixes the
bug — **Resolution slash Fix Notes**, and **Developer Notes** — a place to
record what was actually done, for anyone who looks at this record later.

And finally, the **Redmine** section holds **Redmine Issue ID** and
**Redmine Issue URL** — populated automatically once a report has been
synced, giving a direct link back to the corresponding issue.

---

## PART 6 — How the emails work

Let's go through every situation where Bug Reporter sends an email, since
this is one of the most valuable parts of the whole system — it keeps
people informed without anyone having to check the list manually.

The first email goes out the moment a new Bug Report is created — whether
it came from the manual dialog or from one of the automatic capture paths
makes no difference. That email goes to whoever the report is assigned to,
plus anyone listed in Notification Recipients back in the settings. This
is what makes automatic capture actually useful in practice — a crash
happens, nobody clicked anything, and the right people are already being
told about it within moments.

The second situation is a change in assignment. Whenever a Bug Report gets
reassigned to someone new, that person receives an email letting them know
it's now theirs to work.

The third is resolution. The moment a Bug Report's status is changed to
Resolved, and assuming that setting is turned on in Bug Reporter Settings,
an email goes automatically to the person who originally reported the
bug — letting them know their issue has actually been addressed, without
anyone having to remember to circle back and tell them by hand.

And the fourth is the weekly summary. Once a week, a single email goes out
listing every Bug Report that is still open — still Pending or Reopened —
as one consolidated list. This exists specifically to catch anything that
might have quietly sat untouched between the individual notifications
above — a kind of safety net that runs on its own schedule, independent of
whatever's happening day to day.

Every one of these is best-effort by design — if an email genuinely fails
to send for some reason, that failure is recorded internally, but it never
blocks or breaks the Bug Report itself. The record you're working with
always stays intact, no matter what happens with the notification layer
around it.

---

## PART 7 — A few other things worth knowing

A handful of remaining features round out the app.

There's a simple **Dashboard** page — a quick set of live counts: how many
reports are Pending, how many Critical or High severity ones are still
open, how many have been Reopened, and how many are Resolved. It's meant
for a fast pulse-check, not deep analysis.

We already touched on **duplicate suppression**, but it's worth repeating
because it's one of the more thoughtful parts of the design. The same
underlying error, happening again and again — even across many different
documents in a single bulk operation — collapses into exactly one Bug
Report, not one per occurrence. But the moment a genuinely different error
shows up, even seconds later, that gets its own report. So the system
stays quiet about noise, but never silent about something new.

On **permissions**: System Manager and Bug Reporter Manager both have full
access to everything — creating, editing, deleting, exporting. A Bug
Reporter Tester can create and edit their own reports, but moving something
to Resolved or Rejected is reserved for a Manager or System Manager only —
so the workflow can't be accidentally short-circuited by whoever happened
to file the report.

And that covers the whole application — from the moment someone notices a
problem, or the system notices one on its own, all the way through to a
resolved ticket, an email confirming it, and an optional mirror of the
whole thing living in Redmine too.

---
---

# Screen Guide (not for TTS — keep this separate from what you paste into ElevenLabs)

| Part | What to have on screen |
|---|---|
| 1 | A normal Desk page with the floating "Report Bug" button visible; no clicking needed yet |
| 2 | Click Report Bug, show the dialog fields one at a time as they're mentioned (Title/Description, Severity/Priority pre-filled, Steps to Reproduce, Screenshot, Technical Details expanded), then Submit and show the confirmation |
| 3 | Bug Reporter Settings, scrolled to top — pan down through Enable Report Bug Button, Auto-create Linked Issue, Access, Capture, Automatic Capture, Attachments, Notifications sections in the order narrated |
| 4 | Scroll to / open the Redmine Integration section specifically — show each field as it's named (blur or crop out the actual API key value before recording/sharing), then cut to a synced Bug Report to show "Open in Redmine" and "Sync to Redmine" buttons |
| 5 | Open one real Bug Report record, scroll top to bottom through every section in the order narrated (Details, Evidence, Technical Details, Error Capture, Resolution, Redmine) |
| 6 | Show an Email Queue list or inbox with a couple of example notification emails, or just narrate over the Bug Reporter Settings > Notifications section again |
| 7 | Open the Bug Reporter dashboard page for the counts; optionally show a Bug Report list filtered to Auto-captured for the duplicate-suppression point; show the Allowed Roles table for the permissions point |

**Before recording/sharing:** redact the Redmine API key and, if this is
ever shown outside your organization, the Redmine URL and project
identifier too.
