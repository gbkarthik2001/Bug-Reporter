# Copyright (c) 2026, Your Organization
# License: MIT

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from bug_reporter.utils import (
	find_candidate_error_logs,
	get_installed_apps_summary,
	get_settings,
	safe_get_default_company,
	user_is_manager,
)

# Allowed forward/back transitions. A lean lifecycle by design: Pending
# (open, default) -> Resolved (developer fixed it, emails the reporter -
# see notifications.notify_status_change) -> Reopened (the fix didn't hold)
# or Rejected (won't fix). Rejected -> Pending is the escape hatch for
# reconsidering a rejection.
STATUS_FLOW = {
	"Pending": {"Resolved", "Rejected"},
	"Resolved": {"Reopened"},
	"Reopened": {"Resolved", "Rejected"},
	"Rejected": {"Pending"},
}

# Statuses a plain Tester/reporter is allowed to set themselves (opening a
# new report, or reopening one that wasn't actually fixed). Marking
# something Resolved or Rejected is a developer/manager call.
TESTER_ALLOWED_STATUSES = {"Pending", "Reopened"}


class BugReport(Document):
	def validate(self):
		self._enforce_status_transition()

	def _enforce_status_transition(self):
		if self.is_new():
			self.status = self.status or "Pending"
			return

		previous_status = self.get_doc_before_save()
		if not previous_status or previous_status.status == self.status:
			return

		old, new = previous_status.status, self.status
		allowed_next = STATUS_FLOW.get(old, set())
		if new not in allowed_next and not user_is_manager():
			frappe.throw(
				_("Status cannot move from {0} to {1}.").format(old, new),
				title=_("Invalid Status Transition"),
			)

		if not user_is_manager() and new not in TESTER_ALLOWED_STATUSES and new not in allowed_next:
			frappe.throw(
				_("Only a Bug Reporter Manager can set status to {0}.").format(new)
			)


def before_insert(doc, method=None):
	"""Authoritative, server-side capture. Never trust client-supplied
	values for identity/time fields (spec section 5 & 13)."""
	doc.reported_by = frappe.session.user
	doc.reported_at = now_datetime()
	doc.status = doc.status or "Pending"

	settings = get_settings()
	# NOT "doc.severity or settings...": Severity/Priority are required
	# Select fields with no field-level default (see bug_report.json) so
	# their options stay in sync with Bug Report itself, not duplicated
	# elsewhere - but Frappe's own frappe.new_doc() already auto-fills any
	# defaultless, non-empty Select field with its first listed option
	# before this hook ever runs, so by now doc.severity/doc.priority are
	# NEVER actually falsy and an "or" fallback would silently keep that
	# auto-filled first option forever, ignoring Bug Reporter Settings
	# entirely. Callers that want a genuine user-chosen value (the manual
	# Report Bug dialog, via submit_bug_report) mark that explicitly via
	# doc.flags instead - anything else (auto-capture, or a Bug Report
	# created directly in the desk) always takes the configured default.
	if not doc.flags.get("severity_explicit"):
		doc.severity = settings.get("default_severity")
	if not doc.flags.get("priority_explicit"):
		doc.priority = settings.get("default_priority")

	if not doc.company:
		doc.company = safe_get_default_company(frappe.session.user)

	if not doc.assigned_to and settings.get("default_assignee"):
		doc.assigned_to = settings.get("default_assignee")

	doc.installed_apps = get_installed_apps_summary()

	# Best-effort Error Log correlation - must never block submission.
	if settings.get("enable_error_log_association") and not doc.error_log:
		try:
			candidates = find_candidate_error_logs(reference_time=doc.reported_at)
			if candidates:
				doc.error_log = candidates[0].get("name")
				others = [c.get("name") for c in candidates[1:]]
				if others:
					doc.error_log_candidates = ", ".join(others)
		except Exception:
			frappe.log_error(title="Bug Reporter: correlation in before_insert failed")


def after_insert(doc, method=None):
	# Give the reporter visibility even without broad read permission,
	# and make sure a configured/assigned owner can see + act on it.
	try:
		frappe.share.add_docshare(
			doc.doctype, doc.name, doc.reported_by, read=1, write=0, notify=0
		)
	except Exception:
		pass

	if doc.assigned_to:
		_assign_and_share(doc, doc.assigned_to)

	settings = get_settings()

	if settings.get("auto_create_issue"):
		_create_linked_issue(doc)

	from bug_reporter.notifications import notify_new_bug_report

	frappe.enqueue(
		notify_new_bug_report,
		queue="short",
		enqueue_after_commit=True,
		bug_report_name=doc.name,
	)

	from bug_reporter.redmine import sync_bug_report_to_redmine

	frappe.enqueue(
		sync_bug_report_to_redmine,
		queue="short",
		enqueue_after_commit=True,
		bug_report_name=doc.name,
	)


def on_update(doc, method=None):
	previous = doc.get_doc_before_save()
	if not previous:
		return

	from bug_reporter.notifications import notify_assignment_change, notify_status_change

	if previous.assigned_to != doc.assigned_to and doc.assigned_to:
		_assign_and_share(doc, doc.assigned_to)
		frappe.enqueue(
			notify_assignment_change,
			queue="short",
			enqueue_after_commit=True,
			bug_report_name=doc.name,
		)

	if previous.status != doc.status:
		frappe.enqueue(
			notify_status_change,
			queue="short",
			enqueue_after_commit=True,
			bug_report_name=doc.name,
			old_status=previous.status,
			new_status=doc.status,
		)


def _assign_and_share(doc, user):
	try:
		frappe.share.add_docshare(doc.doctype, doc.name, user, read=1, write=1, notify=0)
	except Exception:
		pass
	try:
		existing = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": doc.doctype,
				"reference_name": doc.name,
				"allocated_to": user,
				"status": "Open",
			},
			limit_page_length=1,
		)
		if not existing:
			# Create the ToDo directly rather than via
			# frappe.desk.form.assign_to.add() - that helper unconditionally
			# fires Frappe's own generic "assigned a new task" notification/
			# email with no way to opt out per-call, which would duplicate
			# our own tailored notify_new_bug_report / notify_assignment_change
			# emails for the exact same event. This still gives the same
			# ToDo-list / Assigned To widget visibility, just without the
			# second email.
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": user,
					"reference_type": doc.doctype,
					"reference_name": doc.name,
					"description": _("Bug Report assigned: {0}").format(doc.title),
					"assigned_by": frappe.session.user,
				}
			).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Bug Reporter: assignment failed")


def _create_linked_issue(doc):
	"""Optionally create a standard Frappe/ERPNext Issue and link it back,
	reusing the existing Issue doctype instead of duplicating it (spec
	sections 10 & 19). No-ops safely if Issue is not part of the site's
	installed doctypes."""
	if not frappe.db.exists("DocType", "Issue"):
		return
	if frappe.db.exists("Issue", {"subject": ["like", f"[{doc.name}]%"]}):
		return
	try:
		issue = frappe.new_doc("Issue")
		issue.subject = f"[{doc.name}] {doc.title}"
		if issue.meta.has_field("description"):
			issue.description = doc.description
		if issue.meta.has_field("raised_by") and doc.reported_by:
			user_email = frappe.db.get_value("User", doc.reported_by, "email")
			issue.raised_by = user_email or doc.reported_by
		issue.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"content": f"Linked Issue created: {issue.name}",
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Bug Reporter: auto Issue creation failed")


@frappe.whitelist()
def get_dashboard_counts():
	"""Lightweight counts for the workspace / dashboard. Respects the
	caller's own permissions via frappe.get_list (not get_all)."""
	from frappe.utils import cint

	def _count(filters):
		return cint(frappe.get_list("Bug Report", filters=filters, limit_page_length=0, fields=["name"]).__len__())

	counts = {
		"pending": _count({"status": "Pending"}),
		"critical_high": _count({"severity": ["in", ["Critical", "High"]], "status": ["not in", ["Resolved", "Rejected"]]}),
		"reopened": _count({"status": "Reopened"}),
		"resolved": _count({"status": "Resolved"}),
	}
	return counts
