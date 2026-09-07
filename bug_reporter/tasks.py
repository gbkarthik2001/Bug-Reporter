# Copyright (c) 2026, Your Organization
# License: MIT

import frappe
from frappe.utils import add_to_date, now_datetime

from bug_reporter.utils import get_settings


def cleanup_old_evidence():
	"""Daily scheduled job (see hooks.scheduler_events). Deletes attached
	files (screenshots/attachments) from Bug Reports that have been in a
	terminal state (Resolved / Rejected) for longer than the configured
	retention window. The Bug Report record itself is kept for audit
	history - only the file evidence is removed.

	No-ops entirely when retention_days is 0 (default = keep forever).
	"""
	settings = get_settings()
	retention_days = frappe.utils.cint(settings.get("retention_days"))
	if retention_days <= 0:
		return

	cutoff = add_to_date(now_datetime(), days=-retention_days)
	terminal_statuses = ["Resolved", "Rejected"]

	old_reports = frappe.get_all(
		"Bug Report",
		filters={
			"status": ["in", terminal_statuses],
			"modified": ["<", cutoff],
		},
		fields=["name"],
		limit_page_length=0,
	)

	for row in old_reports:
		try:
			_remove_evidence(row.name)
		except Exception:
			frappe.log_error(title=f"Bug Reporter: evidence cleanup failed for {row.name}")


def send_weekly_pending_summary():
	"""Weekly scheduled job (see hooks.scheduler_events). Emails the
	configured recipients a list of every Bug Report still open (Pending
	or Reopened), so nothing quietly falls through the cracks between the
	individual new-bug/resolved emails. Skipped entirely when nothing is
	open - an empty reminder isn't useful."""
	pending = frappe.get_all(
		"Bug Report",
		filters={"status": ["in", ["Pending", "Reopened"]]},
		fields=["name", "title", "severity", "status", "reported_by", "creation"],
		limit_page_length=0,
	)
	if not pending:
		return

	severity_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
	pending.sort(key=lambda r: (severity_rank.get(r.severity, 99), r.creation))

	from bug_reporter.notifications import notify_weekly_pending_summary

	notify_weekly_pending_summary(pending)


def _remove_evidence(bug_report_name):
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Bug Report", "attached_to_name": bug_report_name},
		fields=["name"],
	)
	for f in files:
		frappe.delete_doc("File", f.name, ignore_permissions=True, delete_permanently=True)

	frappe.db.set_value("Bug Report", bug_report_name, "screenshot", None, update_modified=False)
	frappe.db.commit()
