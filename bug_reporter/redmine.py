# Copyright (c) 2026, Your Organization
# License: MIT

"""
Optional integration: mirror every new Bug Report into a Redmine issue,
assigned to the Redmine user whose email matches the Bug Report's Assigned
To (falling back to a configured default, or left unassigned).

Deliberately isolated from notifications.py/auto_capture.py, and never
reports its own failures via frappe.log_error(). A Redmine outage or bad
API key must never block Bug Report creation - and for an auto-captured
Bug Report specifically, logging via frappe.log_error() would insert a
new Error Log row and re-trigger bug_reporter.auto_capture.
capture_server_error right back (see that module's docstring for the same
reasoning). All failures here go to the file logger only.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

REQUEST_TIMEOUT = 10


def get_redmine_config():
	"""Returns a plain dict of connection settings, or {} if the
	integration is disabled or not fully configured. Never raises."""
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
	"""Enqueued from Bug Report's after_insert (see bug_report.py). Runs as
	a background job so a slow/unreachable Redmine server never blocks bug
	submission itself. Never raises - this is the automatic, fire-and-forget
	path. For a user-triggered retry/update with real error feedback, see
	manual_sync_to_redmine below."""
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
	"""Called from the "Sync to Redmine" button on the Bug Report form.
	Unlike the automatic after_insert path, this runs synchronously and
	surfaces real errors to the user (a misconfigured setting or an
	unreachable Redmine should be visible here, not silently swallowed) -
	that's the whole point of a manual retry/update button. Creates the
	issue if this report was never synced (e.g. Redmine was down at
	insert time, or sync was disabled then), otherwise pushes the report's
	current field values - including ones that can only change after
	insert, like Assigned To, Steps to Reproduce, Expected/Actual Result -
	onto the existing issue."""
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
	# db_set, not doc.save() - a raw field patch. Bypasses doc_events
	# entirely, so it can't re-fire before_insert/after_insert or
	# re-enqueue notifications for the same Bug Report.
	frappe.db.set_value(
		"Bug Report",
		bug_report_name,
		{"redmine_issue_id": issue_id, "redmine_issue_url": issue_url},
		update_modified=False,
	)
	frappe.db.commit()
	return issue_url


def _build_issue_payload(doc, config, *, include_project_and_tracker):
	"""Shared by both the create path and the update path. project_id/
	tracker_id are only sent on create - resending them on every update
	risks silently moving an issue to a different project/tracker if the
	site's configured project identifier or tracker ID ever changes after
	the issue already exists elsewhere."""
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
	"""Match the Bug Report's Assigned To user to a Redmine user in the
	target project, so the issue lands on the actual developer instead of
	going unassigned/to a generic fallback."""
	if doc.get("assigned_to"):
		email = frappe.db.get_value("User", doc.assigned_to, "email") or doc.assigned_to
		user_id = _find_redmine_user_id_by_email(email, config)
		if user_id:
			return user_id
	return config.get("default_assignee_id")


def _find_redmine_user_id_by_email(email, config):
	"""Match by email against the target project's own member list.

	Deliberately does NOT use Redmine's /users.json search endpoint - that
	requires the API key to belong to a Redmine admin/privileged account,
	which this integration's key is not guaranteed to be. Project
	memberships and individual user lookups (/projects/.../memberships.json,
	/users/:id.json) work for any project member, and login is this
	instance's email address (mail is hidden from non-admin viewers on
	other users' profiles, login is not) - so this works with an ordinary
	project-member API key. Returns None (never raises) if the lookup fails
	or nothing matches, so the caller falls back to the configured default
	assignee."""
	if not email:
		return None

	directory = _get_project_member_directory(config)
	return directory.get(email.lower())


def _get_project_member_directory(config):
	"""{lowercased login: user_id} for every member of the target project.
	Cached for an hour - project membership rarely changes and this avoids
	a fan-out of API calls (one per member) on every single sync."""
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

		# Each member is looked up independently - one member erroring
		# (e.g. a deactivated account 404ing) must not blank out every
		# other member that resolved fine.
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
	"""Redmine's description mirrors exactly four Bug Report fields -
	Description, Steps to Reproduce, Expected Result, Actual Result -
	nothing else (no traceback/route/error dump; those stay in Frappe).

	description and steps_to_reproduce are Text Editor (HTML) fields in
	Frappe - sent raw, Redmine shows the literal tags/entities instead of
	rendering them (its description field is Textile/Markdown, not HTML),
	so both are converted to plain text first. expected_result/
	actual_result are plain Small Text already."""
	from frappe.core.utils import html_to_plain_text

	# Plain-text section labels, not Textile/Markdown heading syntax - this
	# Redmine instance's text formatting mode (Textile vs Markdown) isn't
	# knowable from here, and guessing wrong just swaps one set of literal
	# markup characters for another. Plain text renders cleanly either way.
	sections = [
		("Description", html_to_plain_text(doc.get("description") or "")),
		("Steps to Reproduce", html_to_plain_text(doc.get("steps_to_reproduce") or "")),
		("Expected Result", doc.get("expected_result") or ""),
		("Actual Result", doc.get("actual_result") or ""),
	]
	return "\n\n".join(f"{label}:\n{value}" for label, value in sections if value.strip())


def pull_status_updates():
	"""Scheduled (see hooks.py). For every Bug Report still open here
	(Pending/Reopened) with a linked Redmine issue, check whether that
	issue's Redmine status now matches the configured "resolved" trigger
	status (e.g. "Deployed to UAT") and, if so, move it to Resolved here
	too - one-way (Redmine -> Frappe) and forward-only: never touches a
	Rejected report, never moves anything backward. Never raises - a
	Redmine outage here must not break the scheduler."""
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
