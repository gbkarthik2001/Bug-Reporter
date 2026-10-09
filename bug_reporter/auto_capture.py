# Copyright (c) 2026, Your Organization
# License: MIT

"""Automatic capture of unhandled server-side errors via the Error Log doctype, not a request-level hook."""

import frappe
from frappe.utils import cint

from bug_reporter.utils import (
	build_auto_capture_signature,
	extract_context_from_traceback,
	get_settings,
	is_bug_reporter_enabled,
	safe_get_default_company,
	truncate,
	was_recently_auto_captured,
)


def capture_server_error(doc, method=None):
	"""doc_events["Error Log"]["after_insert"] handler; flag + file-logger guard prevents a re-entrant loop."""
	if frappe.flags.get("in_bug_reporter_auto_capture"):
		return
	frappe.flags.in_bug_reporter_auto_capture = True
	try:
		_capture_server_error(doc)
	except Exception:
		frappe.logger().error("Bug Reporter: auto server-error capture failed", exc_info=True)
	finally:
		frappe.flags.in_bug_reporter_auto_capture = False


# Apps whose Error Log entries never become a Bug Report, even with a real traceback.
EXCLUDED_SOURCE_APPS = {"insights"}


def _is_from_excluded_app(title_source, traceback_text):
	first_segment = (title_source or "").split(".", 1)[0]
	if first_segment in EXCLUDED_SOURCE_APPS:
		return True
	return any(f"/apps/{app}/" in traceback_text for app in EXCLUDED_SOURCE_APPS)


def _capture_server_error(doc):
	if not is_bug_reporter_enabled():
		return

	settings = get_settings()
	if not cint(settings.get("enable_auto_server_capture", 1)):
		return

	# Defensive: skip if this Error Log entry is already about a Bug Report.
	if doc.reference_doctype == "Bug Report":
		return

	traceback_text = doc.error or ""

	if "Traceback" not in traceback_text:
		return

	if _is_from_excluded_app(doc.method, traceback_text):
		return

	# A real crash never sets reference_doctype/name on Error Log - fall back to parsing the traceback's URL.
	route, inferred_doctype, inferred_name = extract_context_from_traceback(traceback_text)
	reference_doctype = doc.reference_doctype or inferred_doctype
	reference_name = (doc.reference_name or inferred_name) if reference_doctype else None

	title_source = doc.method or "Unhandled Server Error"
	# Not scoped per-document - the same bug hitting N records in a bulk op is one report, not N.
	signature = build_auto_capture_signature("server", title_source)
	if was_recently_auto_captured(signature, settings.get("auto_capture_dedup_window_minutes")):
		return

	bug = frappe.new_doc("Bug Report")
	bug.title = truncate(f"[Auto] {title_source}", 140)
	# Escaped explicitly - a traceback can echo attacker-influenced input into this HTML field.
	bug.description = (
		"<p>Automatically captured server error.</p><pre>"
		+ frappe.utils.escape_html(truncate(traceback_text, 5000))
		+ "</pre>"
	)
	bug.error_message = truncate(traceback_text, 500)
	bug.error_log = doc.name
	bug.auto_captured = 1
	bug.correlation_id = signature
	# severity left unset - Bug Report's before_insert fills it from Default Severity.
	bug.route = route
	bug.reference_doctype = reference_doctype
	bug.reference_name = reference_name
	bug.company = safe_get_default_company(doc.owner)

	# Bug Report's own doc_events handle stamping, assignee, sharing, and the notification email.
	bug.insert(ignore_permissions=True)
