# Copyright (c) 2026, Your Organization
# License: MIT

"""Mirrors every new Bug Report into a Redmine issue, assigned by matching email to a project member.

Failures here only go to the file logger, never frappe.log_error() - that would re-trigger auto_capture.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from bug_reporter.utils import is_bug_reporter_enabled

REQUEST_TIMEOUT = 10


def get_redmine_config():
	"""Returns a plain dict of connection settings, or {} if the
	integration is disabled or not fully configured. Never raises."""
	if not is_bug_reporter_enabled():
		return {}

	try:
		settings = frappe.get_cached_doc("Bug Reporter Settings")
	except Exception:
		return {}

	if not cint(settings.get("enable_redmine_sync")):
		return {}

	url = (settings.get("redmine_url") or "").rstrip("/")
	project = settings.get("redmine_project_identifier")
	try:
		api_key = settings.get_password("redmine_api_key", raise_exception=False)
	except Exception:
		api_key = None

	if not (url and project and api_key):
		return {}

	return {
		"url": url,
		"api_key": api_key,
		"project": project,
		"tracker_id": cint(settings.get("redmine_tracker_id")) or 1,
		"default_assignee_id": cint(settings.get("redmine_default_assignee_id")) or None,
		"required_custom_field_id": cint(settings.get("redmine_required_custom_field_id")) or None,
		"required_custom_field_value": settings.get("redmine_required_custom_field_value"),
		"resolved_status_name": settings.get("redmine_resolved_status_name"),
	}


def sync_bug_report_to_redmine(bug_report_name):
	"""Enqueued from Bug Report's after_insert - fire-and-forget, never raises."""
	try:
		_create(bug_report_name)
	except Exception:
		frappe.logger().error(f"Bug Reporter: Redmine sync failed for {bug_report_name}", exc_info=True)


def _create(bug_report_name):
	config = get_redmine_config()
	if not config:
		return

	doc = frappe.get_doc("Bug Report", bug_report_name)
	if doc.get("redmine_issue_id"):
		return  # already synced - defensive, after_insert should only fire once

	payload = _build_issue_payload(doc, config, include_project_and_tracker=True)
	issue_id = _create_issue(config, payload)
	if not issue_id:
		return

	_save_redmine_link(bug_report_name, config, issue_id)


@frappe.whitelist()
def manual_sync_to_redmine(bug_report_name):
	"""Sync to Redmine button handler - runs synchronously and surfaces real errors, unlike auto-sync."""
	frappe.has_permission("Bug Report", "write", doc=bug_report_name, throw=True)

	config = get_redmine_config()
	if not config:
		frappe.throw(
			_("Redmine sync is not enabled, or the Redmine URL / Project Identifier / API Key "
			  "is not fully configured in Bug Reporter Settings."),
			title=_("Redmine Sync Not Configured"),
		)

	doc = frappe.get_doc("Bug Report", bug_report_name)

	if doc.get("redmine_issue_id"):
		payload = _build_issue_payload(doc, config, include_project_and_tracker=False)
		_update_issue(config, doc.redmine_issue_id, payload)
		return {
			"created": False,
			"issue_id": doc.redmine_issue_id,
			"issue_url": doc.redmine_issue_url,
		}

	payload = _build_issue_payload(doc, config, include_project_and_tracker=True)
	issue_id = _create_issue(config, payload)
	if not issue_id:
		frappe.throw(_("Redmine did not return an issue ID for the new issue."))

	issue_url = _save_redmine_link(bug_report_name, config, issue_id)
	return {"created": True, "issue_id": issue_id, "issue_url": issue_url}


def _save_redmine_link(bug_report_name, config, issue_id):
	issue_url = f"{config['url']}/issues/{issue_id}"
	# db_set, not doc.save() - avoids re-firing doc_events for this Bug Report.
	frappe.db.set_value(
		"Bug Report",
		bug_report_name,
		{"redmine_issue_id": issue_id, "redmine_issue_url": issue_url},
		update_modified=False,
	)
	frappe.db.commit()
	return issue_url


def _build_issue_payload(doc, config, *, include_project_and_tracker):
	"""project_id/tracker_id are sent only on create, never on update - resending risks moving the issue."""
	issue = {
		"subject": doc.title,
		"description": _build_description(doc),
	}
	if include_project_and_tracker:
		issue["project_id"] = config["project"]
		issue["tracker_id"] = config["tracker_id"]

	assignee_id = _resolve_assignee_id(doc, config)
	if assignee_id:
		issue["assigned_to_id"] = assignee_id

	if config.get("required_custom_field_id") and config.get("required_custom_field_value"):
		issue["custom_fields"] = [
			{"id": config["required_custom_field_id"], "value": config["required_custom_field_value"]}
		]

	return {"issue": issue}


def _create_issue(config, payload):
	import requests

	response = requests.post(
		f"{config['url']}/issues.json",
		data=json.dumps(payload),
		headers={
			"Content-Type": "application/json",
			"X-Redmine-API-Key": config["api_key"],
		},
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()
	issue = (response.json() or {}).get("issue") or {}
	return issue.get("id")


def _update_issue(config, issue_id, payload):
	import requests

	response = requests.put(
		f"{config['url']}/issues/{issue_id}.json",
		data=json.dumps(payload),
		headers={
			"Content-Type": "application/json",
			"X-Redmine-API-Key": config["api_key"],
		},
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()


def _resolve_assignee_id(doc, config):
	"""Match Bug Report's Assigned To to a Redmine user, falling back to the configured default."""
	if doc.get("assigned_to"):
		email = frappe.db.get_value("User", doc.assigned_to, "email") or doc.assigned_to
		user_id = _find_redmine_user_id_by_email(email, config)
		if user_id:
			return user_id
	return config.get("default_assignee_id")


def _find_redmine_user_id_by_email(email, config):
	"""Match by email via project membership lookups, not /users.json - that needs an admin API key."""
	if not email:
		return None

	directory = _get_project_member_directory(config)
	return directory.get(email.lower())


def _get_project_member_directory(config):
	"""{lowercased login: user_id} for the project, cached an hour to avoid a per-sync API fan-out."""
	import requests

	cache_key = f"bug_reporter_redmine_member_directory::{config['project']}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	directory = {}
	try:
		response = requests.get(
			f"{config['url']}/projects/{config['project']}/memberships.json",
			headers={"X-Redmine-API-Key": config["api_key"]},
			params={"limit": 100},
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		memberships = (response.json() or {}).get("memberships") or []
	except Exception:
		frappe.logger().error(
			f"Bug Reporter: Redmine project membership lookup failed for {config['project']}",
			exc_info=True,
		)
		return {}

	for membership in memberships:
		user = membership.get("user")
		if not user or not user.get("id"):
			continue  # group membership, not an individual user

		# Looked up independently - one member erroring must not blank out the rest.
		try:
			user_response = requests.get(
				f"{config['url']}/users/{user['id']}.json",
				headers={"X-Redmine-API-Key": config["api_key"]},
				timeout=REQUEST_TIMEOUT,
			)
			user_response.raise_for_status()
			login = ((user_response.json() or {}).get("user") or {}).get("login")
			if login:
				directory[login.lower()] = user["id"]
		except Exception:
			frappe.logger().error(
				f"Bug Reporter: Redmine user lookup failed for member {user.get('id')} "
				f"({user.get('name')}) in project {config['project']}",
				exc_info=True,
			)
			continue

	frappe.cache().set_value(cache_key, directory, expires_in_sec=3600)
	return directory


def _build_description(doc):
	"""Mirrors Description/Steps/Expected/Actual only; HTML fields are converted to plain text first."""
	from frappe.core.utils import html_to_plain_text

	# Plain-text labels, not Textile/Markdown headings - Redmine's text mode isn't knowable from here.
	sections = [
		("Description", html_to_plain_text(doc.get("description") or "")),
		("Steps to Reproduce", html_to_plain_text(doc.get("steps_to_reproduce") or "")),
		("Expected Result", doc.get("expected_result") or ""),
		("Actual Result", doc.get("actual_result") or ""),
	]
	return "\n\n".join(f"{label}:\n{value}" for label, value in sections if value.strip())


def pull_status_updates():
	"""Scheduled: moves open Bug Reports to Resolved when their linked Redmine issue hits the trigger status, one-way and forward-only."""
	config = get_redmine_config()
	if not config or not config.get("resolved_status_name"):
		return

	candidates = frappe.get_all(
		"Bug Report",
		filters={
			"redmine_issue_id": ["is", "set"],
			"status": ["in", ["Pending", "Reopened"]],
		},
		fields=["name", "redmine_issue_id"],
	)
	for row in candidates:
		try:
			_pull_status_for_one(row.name, row.redmine_issue_id, config)
		except Exception:
			frappe.logger().error(
				f"Bug Reporter: Redmine status pull failed for {row.name}", exc_info=True
			)


def _pull_status_for_one(bug_report_name, issue_id, config):
	import requests

	response = requests.get(
		f"{config['url']}/issues/{issue_id}.json",
		headers={"X-Redmine-API-Key": config["api_key"]},
		timeout=REQUEST_TIMEOUT,
	)
	response.raise_for_status()
	status_name = ((response.json() or {}).get("issue") or {}).get("status", {}).get("name")

	if status_name != config["resolved_status_name"]:
		return

	doc = frappe.get_doc("Bug Report", bug_report_name)
	if doc.status not in ("Pending", "Reopened"):
		return  # changed locally since the candidates query ran

	doc.status = "Resolved"
	doc.add_comment(
		"Info",
		_("Automatically marked Resolved - linked Redmine issue #{0} reached status \"{1}\".").format(
			issue_id, status_name
		),
	)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
