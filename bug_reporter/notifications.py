# Copyright (c) 2026, Your Organization
# License: MIT

"""
Notification helpers. Run inside background jobs (see doc_events in
hooks.py) so a slow SMTP server never blocks bug submission itself.

Deliberately keeps sensitive technical detail (stack traces, raw error
text) out of the email subject line (spec section 11) and links back
to the record instead of inlining everything.
"""

import frappe
from frappe import _

from bug_reporter.utils import get_settings


def _recipients_from_settings():
	try:
		settings = frappe.get_cached_doc("Bug Reporter Settings")
		return [row.user for row in (settings.notification_recipients or []) if row.user]
	except Exception:
		return []


def _doc_url(bug_report_name):
	return frappe.utils.get_url_to_form("Bug Report", bug_report_name)


def notify_new_bug_report(bug_report_name):
	doc = frappe.get_doc("Bug Report", bug_report_name)
	recipients = set(_recipients_from_settings())

	settings = get_settings()
	if settings.get("default_assignee"):
		recipients.add(settings.get("default_assignee"))
	if doc.assigned_to:
		recipients.add(doc.assigned_to)

	recipients.discard(doc.reported_by)
	emails = _emails_for([r for r in recipients if r])
	if not emails:
		return

	is_auto = bool(doc.get("auto_captured"))
	subject = _(f"Auto-captured Error: {doc.name}") if is_auto else _(f"New Bug Report: {doc.name}")
	message = frappe.render_template(
		"""
		<p>{{ intro }}</p>
		<ul>
			<li><b>Bug ID:</b> {{ name }}</li>
			<li><b>Title:</b> {{ title }}</li>
			<li><b>Severity:</b> {{ severity }} &nbsp; <b>Priority:</b> {{ priority }}</li>
			<li><b>Route:</b> {{ route }}</li>
			<li><b>Reported By:</b> {{ reported_by }}</li>
		</ul>
		<p><a href="{{ url }}">Open the bug report</a></p>
		""",
		{
			"intro": _("A server or browser error was captured automatically - no one reported this manually.")
			if is_auto
			else _("A new bug report has been submitted."),
			"name": doc.name,
			"title": doc.title,
			"severity": doc.severity,
			"priority": doc.priority,
			"route": doc.route,
			"reported_by": doc.reported_by,
			"url": _doc_url(doc.name),
		},
	)
	attachments = [{"file_url": doc.screenshot}] if doc.get("screenshot") else None
	_safe_sendmail(emails, subject, message, attachments=attachments)

	try:
		frappe.publish_realtime(
			event="bug_reporter_new_report",
			message={"name": doc.name, "title": doc.title},
			user=None,
			after_commit=True,
		)
	except Exception:
		pass


def notify_assignment_change(bug_report_name):
	doc = frappe.get_doc("Bug Report", bug_report_name)
	if not doc.assigned_to:
		return
	emails = _emails_for([doc.assigned_to])
	if not emails:
		return
	subject = _(f"Bug Report {doc.name} assigned to you")
	message = frappe.render_template(
		"""
		<p>{{ title }} has been assigned to you.</p>
		<p><a href="{{ url }}">Open the bug report</a></p>
		""",
		{"title": doc.title, "url": _doc_url(doc.name)},
	)
	_safe_sendmail(emails, subject, message)


def notify_status_change(bug_report_name, old_status, new_status):
	doc = frappe.get_doc("Bug Report", bug_report_name)
	settings = get_settings()

	# The one status change the reporter actually needs to hear about
	# unprompted: the developer marked it Resolved. Reopened/Rejected are
	# visible to whoever's watching the record already; this is the "you can
	# stop waiting" notification.
	if new_status == "Resolved" and settings.get("notify_tester_on_close"):
		emails = _emails_for([doc.reported_by])
		if emails:
			subject = _(f"Bug Report {doc.name} marked Resolved")
			message = frappe.render_template(
				"""
				<p>Your bug report <b>{{ title }}</b> has been marked <b>Resolved</b>.</p>
				<p><a href="{{ url }}">Open the bug report</a></p>
				""",
				{"title": doc.title, "url": _doc_url(doc.name)},
			)
			_safe_sendmail(emails, subject, message)


def notify_weekly_pending_summary(pending_reports):
	"""Called from tasks.send_weekly_pending_summary (see hooks.py's
	scheduler_events["weekly"]). pending_reports is a list of dicts (name,
	title, severity, status, reported_by) already filtered to Pending/
	Reopened and sorted worst-first by the caller. Reuses the same
	recipient list as new-bug notifications - no separate settings needed."""
	recipients = set(_recipients_from_settings())
	settings = get_settings()
	if settings.get("default_assignee"):
		recipients.add(settings.get("default_assignee"))
	emails = _emails_for([r for r in recipients if r])
	if not emails:
		return

	esc = frappe.utils.escape_html
	rows = "".join(
		"<tr>"
		f"<td><a href='{_doc_url(r.name)}'>{esc(r.name)}</a></td>"
		f"<td>{esc(r.title)}</td>"
		f"<td>{esc(r.severity)}</td>"
		f"<td>{esc(r.status)}</td>"
		f"<td>{esc(r.reported_by)}</td>"
		"</tr>"
		for r in pending_reports
	)
	subject = _(f"Weekly Bug Reporter reminder: {len(pending_reports)} still open")
	message = (
		f"<p>{len(pending_reports)} Bug Report(s) are still open (Pending or Reopened):</p>"
		'<table border="1" cellpadding="6" style="border-collapse:collapse; width:100%;">'
		"<thead><tr><th>ID</th><th>Title</th><th>Severity</th><th>Status</th><th>Reported By</th></tr></thead>"
		f"<tbody>{rows}</tbody>"
		"</table>"
	)
	_safe_sendmail(emails, subject, message)


def _emails_for(users):
	emails = []
	for user in users:
		if not user or user == "Guest":
			continue
		email = frappe.db.get_value("User", user, "email")
		if email:
			emails.append(email)
	return emails


def _safe_sendmail(recipients, subject, message, attachments=None):
	if not recipients:
		return
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=message, attachments=attachments)
	except Exception:
		frappe.log_error(title="Bug Reporter: notification email failed")
