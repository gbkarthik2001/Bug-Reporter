# Copyright (c) 2026, Your Organization
# License: MIT

"""
All endpoints the browser widget talks to. Kept deliberately small and
defensive: nothing here should ever raise an exception that prevents a
tester from submitting a bug report (spec section 7 / 19).
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

from bug_reporter.utils import (
	build_auto_capture_signature,
	get_settings,
	log_client_error_to_error_log,
	parse_user_agent,
	safe_json_loads,
	truncate,
	user_can_submit,
	was_recently_auto_captured,
)

MAX_CLIENT_ERRORS = 20
MAX_FAILED_REQUESTS = 20
MAX_FIELD_LEN = 140


@frappe.whitelist()
def get_report_context():
	"""Non-sensitive settings + permission check the widget needs before
	it even shows the button/dialog."""
	settings = get_settings()
	bug_report_meta = frappe.get_meta("Bug Report")
	return {
		"can_submit": user_can_submit(),
		"enabled": bool(cint(settings.get("enabled"))),
		"client_error_capture_enabled": bool(cint(settings.get("enable_client_error_capture"))),
		# Bug Report's own Severity/Priority fields are the single source of
		# truth for the option lists (not duplicated in the dialog's JS),
		# Bug Reporter Settings' Default Severity/Priority are the single
		# source of truth for which one is pre-selected.
		"severity_options": bug_report_meta.get_field("severity").options,
		"priority_options": bug_report_meta.get_field("priority").options,
		"default_severity": settings.get("default_severity"),
		"default_priority": settings.get("default_priority"),
	}


@frappe.whitelist()
def submit_bug_report(payload):
	"""Single entry point used by the Report Bug dialog. `payload` is a
	JSON string built client-side; every value is treated as untrusted
	input and re-validated/truncated here. Identity and timestamp fields
	are never taken from the payload (see bug_report.before_insert)."""
	if not user_can_submit():
		frappe.throw(_("You do not have permission to submit bug reports."), frappe.PermissionError)

	data = safe_json_loads(payload, default={})
	if not isinstance(data, dict):
		frappe.throw(_("Invalid bug report payload."))

	title = (data.get("title") or "").strip()
	description = (data.get("description") or "").strip()
	if not title or not description:
		frappe.throw(_("Title and Description are required."))

	user_agent = data.get("user_agent") or ""
	browser, os_name = parse_user_agent(user_agent)

	doc = frappe.new_doc("Bug Report")
	doc.title = title[:MAX_FIELD_LEN]
	doc.description = description
	doc.expected_result = data.get("expected_result")
	doc.actual_result = data.get("actual_result")
	doc.steps_to_reproduce = data.get("steps_to_reproduce")
	if data.get("severity"):
		doc.severity = data.get("severity")
		doc.flags.severity_explicit = True
	if data.get("priority"):
		doc.priority = data.get("priority")
		doc.flags.priority_explicit = True
	doc.route = (data.get("route") or "")[:255]
	doc.reference_doctype = _safe_doctype(data.get("reference_doctype"))
	doc.reference_name = data.get("reference_name") if doc.reference_doctype else None
	doc.browser = browser
	doc.operating_system = os_name
	doc.user_agent = user_agent[:500]
	doc.correlation_id = (data.get("correlation_id") or frappe.generate_hash(length=10))[:40]
	doc.error_message = (data.get("error_message") or "")[:500]

	client_errors = data.get("client_errors") or []
	if isinstance(client_errors, list):
		doc.client_errors = json.dumps(client_errors[:MAX_CLIENT_ERRORS])

	failed_requests = data.get("failed_requests") or []
	if isinstance(failed_requests, list):
		doc.failed_requests = json.dumps(failed_requests[:MAX_FAILED_REQUESTS])

	if data.get("screenshot"):
		doc.screenshot = data.get("screenshot")

	doc.insert(ignore_permissions=True)

	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
@rate_limit(limit=20, seconds=60)
def report_client_error(payload):
	"""Fully automatic counterpart to submit_bug_report - called by
	bug_reporter_capture.js itself the moment an uncaught JS error / unhandled
	promise rejection happens, no "Report Bug" click involved. Deliberately
	requires a logged-in session (not allow_guest) and is rate-limited, since
	unlike the manual dialog this fires with zero human judgement in front of
	it and a broken page could otherwise call it in a tight loop."""
	settings = get_settings()
	if not cint(settings.get("enable_auto_client_capture", 1)):
		return {"captured": False}

	if frappe.session.user == "Guest":
		return {"captured": False}

	data = safe_json_loads(payload, default={})
	if not isinstance(data, dict):
		return {"captured": False}

	message = (data.get("message") or "").strip()
	if not message:
		return {"captured": False}

	reference_doctype = _safe_doctype(data.get("reference_doctype"))
	reference_name = data.get("reference_name") if reference_doctype else None

	# Scoped to the specific record when one is known - the same JS error
	# recurring on the very same document is a duplicate; the same error
	# on a *different* document is a distinct, real occurrence and must
	# still get its own report (matches the same-record dedup scoping in
	# auto_capture.py's server-side path).
	signature_key = f"{message}|{reference_doctype}:{reference_name}" if reference_doctype else message
	signature = build_auto_capture_signature("client", signature_key)
	if was_recently_auto_captured(signature, settings.get("auto_capture_dedup_window_minutes")):
		return {"captured": False, "reason": "duplicate"}

	user_agent = data.get("user_agent") or ""
	browser, os_name = parse_user_agent(user_agent)

	doc = frappe.new_doc("Bug Report")
	doc.title = truncate(f"[Auto] Client error: {message}", MAX_FIELD_LEN)
	doc.description = "<p>Automatically captured browser error.</p><pre>" + frappe.utils.escape_html(
		truncate(message, 2000)
	) + "</pre>"
	doc.error_message = truncate(message, 500)
	doc.auto_captured = 1
	doc.correlation_id = signature
	# severity intentionally left unset here - Bug Report's own before_insert
	# fills it from Bug Reporter Settings' Default Severity (single source
	# of truth, not a value hardcoded per capture path).
	doc.route = (data.get("route") or "")[:255]
	doc.reference_doctype = reference_doctype
	doc.reference_name = reference_name
	doc.browser = browser
	doc.operating_system = os_name
	doc.user_agent = user_agent[:500]

	client_errors = data.get("client_errors") or []
	if isinstance(client_errors, list):
		doc.client_errors = json.dumps(client_errors[:MAX_CLIENT_ERRORS])

	failed_requests = data.get("failed_requests") or []
	if isinstance(failed_requests, list):
		doc.failed_requests = json.dumps(failed_requests[:MAX_FAILED_REQUESTS])

	# doc_events on Bug Report already stamp reported_by/reported_at, default
	# the assignee, share the record, and enqueue the new-report email.
	doc.insert(ignore_permissions=True)

	return {"captured": True, "name": doc.name}


@frappe.whitelist()
def log_client_error(correlation_id, message):
	"""Optional lightweight endpoint: mirrors a client-side error into
	Frappe's Error Log immediately (rather than waiting for submission)
	so it is timestamped close to when it actually happened, improving
	correlation accuracy. Called sparingly and rate-limited client-side."""
	if not correlation_id or not message:
		return
	message = str(message)[:2000]
	correlation_id = str(correlation_id)[:40]
	log_client_error_to_error_log(correlation_id, message)


def _safe_doctype(doctype):
	if not doctype:
		return None
	try:
		if frappe.db.exists("DocType", doctype):
			return doctype
	except Exception:
		pass
	return None
