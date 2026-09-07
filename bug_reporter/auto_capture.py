# Copyright (c) 2026, Your Organization
# License: MIT

"""
Fully automatic capture of unhandled *server-side* errors - no "Report Bug"
click involved.

Why hook on the "Error Log" doctype rather than Frappe's request-level
exception handler: Frappe only ever writes to its own core Error Log for
genuinely unhandled exceptions (frappe/app.py's handle_exception logs there
only when `http_status_code >= 500`) or when application code explicitly
calls frappe.log_error() on something it caught. Routine frappe.throw()
validation/permission messages (417/403/404/...) never reach Error Log at
all - so hooking here already gives us "unhandled crashes, not routine
validation noise" for free, without needing to monkeypatch frappe.app or
frappe.utils.error directly.
"""

import frappe
from frappe.utils import cint

from bug_reporter.utils import (
	build_auto_capture_signature,
	extract_context_from_traceback,
	get_settings,
	safe_get_default_company,
	truncate,
	was_recently_auto_captured,
)


def capture_server_error(doc, method=None):
	"""doc_events["Error Log"]["after_insert"] handler.

	Re-entrancy guard: bug.insert() below runs Bug Report's OWN
	before_insert/after_insert (sharing, assignment, frappe.enqueue(...) for
	the notification email). If any of that raises for any reason - e.g. the
	queue/Redis being unreachable, confirmed in testing to actually raise
	rather than fail silently - the exception propagates back out of
	bug.insert() into this function. Logging that failure via
	frappe.log_error() would itself insert a new Error Log row, which would
	re-trigger this very handler: an Error-Log-creates-Bug-Report-fails-
	writes-Error-Log loop. So (a) this failure is logged to the file logger,
	never frappe.log_error/Error Log, and (b) a flag blocks any nested
	re-entry outright as a second, independent line of defense.
	"""
	if frappe.flags.get("in_bug_reporter_auto_capture"):
		return
	frappe.flags.in_bug_reporter_auto_capture = True
	try:
		_capture_server_error(doc)
	except Exception:
		frappe.logger().error("Bug Reporter: auto server-error capture failed", exc_info=True)
	finally:
		frappe.flags.in_bug_reporter_auto_capture = False


def _capture_server_error(doc):
	settings = get_settings()
	if not cint(settings.get("enable_auto_server_capture", 1)):
		return

	# Guard against feedback loops: nothing in the Bug Report creation path
	# below should be able to write back to Error Log in a way that
	# re-triggers this handler, but skip defensively all the same if this
	# Error Log entry is already about a Bug Report.
	if doc.reference_doctype == "Bug Report":
		return

	traceback_text = doc.error or ""

	# The Error Log itself never carries reference_doctype/reference_name
	# for a real crash (see module docstring) - fall back to parsing the
	# failing request's own URL out of the traceback text. Still prefer
	# doc.reference_doctype/doc.reference_name where some other code path
	# *did* set them explicitly (e.g. a direct frappe.log_error(...,
	# reference_doctype=...) call elsewhere in the codebase). Computed
	# before the dedup check (not after, as before) so the signature below
	# can be scoped per-record, not just per-error-message.
	route, inferred_doctype, inferred_name = extract_context_from_traceback(traceback_text)
	reference_doctype = doc.reference_doctype or inferred_doctype
	reference_name = (doc.reference_name or inferred_name) if reference_doctype else None

	title_source = doc.method or "Unhandled Server Error"
	# Scoped to the specific record when one is known (e.g. "same method
	# failing again on the very same EOI Form" is a duplicate; the same
	# method failing on a *different* EOI Form is a distinct, real
	# occurrence and must still get its own report) - falls back to the
	# method name alone when no record could be identified.
	signature_key = f"{title_source}|{reference_doctype}:{reference_name}" if reference_doctype else title_source
	signature = build_auto_capture_signature("server", signature_key)
	if was_recently_auto_captured(signature, settings.get("auto_capture_dedup_window_minutes")):
		return

	bug = frappe.new_doc("Bug Report")
	bug.title = truncate(f"[Auto] {title_source}", 140)
	# Escaped explicitly rather than relying on template auto-escaping - a
	# traceback can echo back attacker-influenced input (e.g. raise
	# ValueError(some_user_value)), and this becomes raw HTML in a Text
	# Editor field seen by whoever opens the report.
	bug.description = (
		"<p>Automatically captured server error.</p><pre>"
		+ frappe.utils.escape_html(truncate(traceback_text, 5000))
		+ "</pre>"
	)
	bug.error_message = truncate(traceback_text, 500)
	bug.error_log = doc.name
	bug.auto_captured = 1
	bug.correlation_id = signature
	# severity intentionally left unset here - Bug Report's own before_insert
	# fills it from Bug Reporter Settings' Default Severity (single source
	# of truth, not a value hardcoded per capture path).
	bug.route = route
	bug.reference_doctype = reference_doctype
	bug.reference_name = reference_name
	bug.company = safe_get_default_company(doc.owner)

	# doc_events on Bug Report (before_insert/after_insert) already take
	# care of: stamping reported_by/reported_at from the current session,
	# defaulting assignee, sharing, and enqueueing the new-report email -
	# nothing further needed here.
	bug.insert(ignore_permissions=True)
