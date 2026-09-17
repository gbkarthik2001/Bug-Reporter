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

# --- email design ----------------------------------------------------
# Gmail and most other clients strip <style> blocks and don't reliably
# support modern CSS, so every one of these emails is a plain HTML
# table with every style attribute written inline - the only layout
# approach that renders consistently across clients. Kept as small,
# reusable pieces below rather than duplicating this markup in each
# notify_* function.

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

_SEVERITY_COLORS = {
	"Critical": ("#fee2e2", "#b91c1c"),
	"High": ("#ffedd5", "#c2410c"),
	"Medium": ("#fef9c3", "#a16207"),
	"Low": ("#e5e7eb", "#4b5563"),
}


def _badge(text, bg, fg):
	if not text:
		return ""
	return (
		f'<span style="display:inline-block;background:{bg};color:{fg};'
		f'font-size:12px;font-weight:600;padding:3px 10px;border-radius:12px;">'
		f"{frappe.utils.escape_html(text)}</span>"
	)


def _severity_badge(severity):
	bg, fg = _SEVERITY_COLORS.get(severity, ("#e5e7eb", "#4b5563"))
	return _badge(severity, bg, fg)


def _button(url, label):
	return (
		f'<a href="{url}" style="display:inline-block;background:#1f6bff;color:#ffffff;'
		f"text-decoration:none;padding:11px 22px;border-radius:6px;font-size:14px;"
		f'font-weight:600;font-family:{_FONT};">{frappe.utils.escape_html(label)} &rarr;</a>'
	)


def _info_row(label, value_html):
	if not value_html:
		return ""
	return (
		'<tr>'
		f'<td style="padding:9px 0;color:#6b7280;font-size:13px;width:110px;'
		f'vertical-align:top;font-family:{_FONT};">{frappe.utils.escape_html(label)}</td>'
		f'<td style="padding:9px 0;color:#111827;font-size:13px;font-family:{_FONT};">{value_html}</td>'
		"</tr>"
	)


def _email_shell(heading, subheading, accent, body_html):
	"""The shared card: a colored header band, a white content card below
	it, and a small footer - body_html is whatever each notify_* function
	builds (info rows, a button, a table, plain text)."""
	return f"""
	<div style="font-family:{_FONT};max-width:560px;margin:0 auto;background:#ffffff;">
		<div style="background:{accent};padding:22px 24px;border-radius:10px 10px 0 0;">
			<div style="color:#ffffff;font-size:11px;font-weight:700;letter-spacing:0.6px;
				text-transform:uppercase;opacity:0.85;">Bug Reporter</div>
			<div style="color:#ffffff;font-size:19px;font-weight:700;margin-top:6px;">
				{frappe.utils.escape_html(heading)}</div>
			{f'<div style="color:#ffffff;font-size:13px;margin-top:4px;opacity:0.9;">{frappe.utils.escape_html(subheading)}</div>' if subheading else ""}
		</div>
		<div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;padding:24px;">
			{body_html}
		</div>
		<div style="text-align:center;padding:14px 0;color:#9ca3af;font-size:11px;font-family:{_FONT};">
			Sent automatically by Bug Reporter
		</div>
	</div>
	"""


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
	intro = (
		_("A server or browser error was captured automatically - no one reported this manually.")
		if is_auto
		else _("A new bug report has been submitted.")
	)
	priority_value = f"{doc.priority}" if doc.priority else ""
	body = f"""
		<p style="margin:0 0 18px 0;color:#374151;font-size:14px;line-height:1.5;font-family:{_FONT};">
			{frappe.utils.escape_html(intro)}
		</p>
		<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #f0f1f3;">
			{_info_row(_("Bug ID"), frappe.utils.escape_html(doc.name))}
			{_info_row(_("Title"), frappe.utils.escape_html(doc.title or ""))}
			{_info_row(_("Severity"), _severity_badge(doc.severity) + (f"&nbsp;&nbsp;{_badge(priority_value, '#dbeafe', '#1e40af')}" if priority_value else ""))}
			{_info_row(_("Route"), f'<code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:12px;">{frappe.utils.escape_html(doc.route or "-")}</code>')}
			{_info_row(_("Reported By"), frappe.utils.escape_html(doc.reported_by or ""))}
		</table>
		<div style="margin-top:22px;">{_button(_doc_url(doc.name), _("Open the Bug Report"))}</div>
	"""
	message = _email_shell(
		_("Auto-captured Error") if is_auto else _("New Bug Report"),
		doc.name,
		"#dc2626" if is_auto else "#1f6bff",
		body,
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
	body = f"""
		<table cellpadding="0" cellspacing="0" style="width:100%;border-top:1px solid #f0f1f3;margin-bottom:18px;">
			{_info_row(_("Bug ID"), frappe.utils.escape_html(doc.name))}
			{_info_row(_("Title"), frappe.utils.escape_html(doc.title or ""))}
			{_info_row(_("Severity"), _severity_badge(doc.severity))}
		</table>
		{_button(_doc_url(doc.name), _("Open the Bug Report"))}
	"""
	message = _email_shell(_("Assigned to You"), doc.name, "#7c3aed", body)
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
			body = f"""
				<p style="margin:0 0 18px 0;color:#374151;font-size:14px;line-height:1.5;font-family:{_FONT};">
					{_("Your bug report")} <b>{frappe.utils.escape_html(doc.title or doc.name)}</b>
					{_("has been marked")} {_badge(_("Resolved"), "#dcfce7", "#15803d")}.
				</p>
				{_button(_doc_url(doc.name), _("Open the Bug Report"))}
			"""
			message = _email_shell(_("Bug Resolved"), doc.name, "#16a34a", body)
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
	_cell = f"padding:10px 12px;font-size:13px;color:#111827;font-family:{_FONT};border-bottom:1px solid #f0f1f3;"
	_head = (
		f"padding:9px 12px;font-size:11px;font-weight:700;letter-spacing:0.4px;text-transform:uppercase;"
		f"color:#6b7280;font-family:{_FONT};border-bottom:1px solid #e5e7eb;text-align:left;"
	)
	rows = "".join(
		"<tr>"
		f"<td style='{_cell}'><a href='{_doc_url(r.name)}' style='color:#1f6bff;text-decoration:none;font-weight:600;'>{esc(r.name)}</a></td>"
		f"<td style='{_cell}'>{esc(r.title)}</td>"
		f"<td style='{_cell}'>{_severity_badge(r.severity)}</td>"
		f"<td style='{_cell}'>{esc(r.status)}</td>"
		f"<td style='{_cell}'>{esc(r.reported_by)}</td>"
		"</tr>"
		for r in pending_reports
	)
	subject = _(f"Weekly Bug Reporter reminder: {len(pending_reports)} still open")
	body = f"""
		<p style="margin:0 0 16px 0;color:#374151;font-size:14px;line-height:1.5;font-family:{_FONT};">
			<b>{len(pending_reports)}</b> {_("Bug Report(s) are still open (Pending or Reopened):")}
		</p>
		<table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
			<thead><tr>
				<th style="{_head}">{_("ID")}</th>
				<th style="{_head}">{_("Title")}</th>
				<th style="{_head}">{_("Severity")}</th>
				<th style="{_head}">{_("Status")}</th>
				<th style="{_head}">{_("Reported By")}</th>
			</tr></thead>
			<tbody>{rows}</tbody>
		</table>
	"""
	message = _email_shell(_("Weekly Pending Summary"), None, "#ea580c", body)
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
