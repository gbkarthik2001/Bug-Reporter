# Copyright (c) 2026, Your Organization
# License: MIT

import frappe


ROLES = [
	{
		"role_name": "Bug Reporter Tester",
		"desk_access": 1,
		"description": "Can submit bug reports and view their own submissions.",
	},
	{
		"role_name": "Bug Reporter Manager",
		"desk_access": 1,
		"description": "Can triage, assign, investigate, and close bug reports.",
	},
]


def after_install():
	_create_roles()
	_create_default_settings()
	_grant_role_to_admin()
	frappe.db.commit()
	print("Bug Reporter: installation complete. Configure defaults under 'Bug Reporter Settings'.")


def before_uninstall():
	# Deliberately conservative: we do not delete Bug Report data or the
	# Roles on uninstall, since bug history has ongoing audit value even
	# after the app is removed. Document this clearly for admins.
	frappe.msgprint(
		"Bug Reporter has been removed. Existing Bug Report records, the "
		"Bug Reporter Tester/Manager roles, and any linked Issues have "
		"been left in place. Remove them manually if a full cleanup is required.",
		alert=True,
	)


def _create_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role["role_name"]):
			doc = frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role["role_name"],
					"desk_access": role["desk_access"],
				}
			)
			doc.insert(ignore_permissions=True)


def _create_default_settings():
	if not frappe.db.exists("Bug Reporter Settings", "Bug Reporter Settings"):
		return
	settings = frappe.get_single("Bug Reporter Settings")
	if settings.get("__islocal") or not settings.enabled:
		settings.enabled = 1
		settings.enable_client_error_capture = 1
		settings.enable_error_log_association = 1
		settings.default_severity = settings.default_severity or "Medium"
		settings.default_priority = settings.default_priority or "Medium"
		settings.error_log_correlation_window_minutes = settings.error_log_correlation_window_minutes or 10
		settings.notify_tester_on_close = 1
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)


def _grant_role_to_admin():
	try:
		user = frappe.get_doc("User", "Administrator")
		existing_roles = {r.role for r in user.roles}
		changed = False
		for role_name in ("Bug Reporter Tester", "Bug Reporter Manager"):
			if role_name not in existing_roles:
				user.append("roles", {"role": role_name})
				changed = True
		if changed:
			user.save(ignore_permissions=True)
	except Exception:
		pass
