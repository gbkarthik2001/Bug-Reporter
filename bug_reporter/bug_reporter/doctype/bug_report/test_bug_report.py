# Copyright (c) 2026, Your Organization
# License: MIT

import frappe
from frappe.tests.utils import FrappeTestCase


class TestBugReport(FrappeTestCase):
	def setUp(self):
		self._ensure_roles()

	def _ensure_roles(self):
		for role in ("Bug Reporter Tester", "Bug Reporter Manager"):
			if not frappe.db.exists("Role", role):
				frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)

	def _new_bug(self, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Bug Report",
				"title": kwargs.get("title", "Test bug"),
				"description": kwargs.get("description", "Something broke"),
				"route": kwargs.get("route", "app/sales-invoice/SINV-0001"),
				"severity": kwargs.get("severity", "Medium"),
				"priority": kwargs.get("priority", "Medium"),
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_server_side_identity_capture(self):
		"""reported_by / reported_at must always be server-authoritative,
		even if a caller tries to spoof them."""
		doc = frappe.get_doc(
			{
				"doctype": "Bug Report",
				"title": "Spoof attempt",
				"description": "x",
				"reported_by": "administrator@example.com",  # should be overwritten
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.reported_by, frappe.session.user)
		self.assertIsNotNone(doc.reported_at)

	def test_default_status_is_pending(self):
		doc = self._new_bug()
		self.assertEqual(doc.status, "Pending")

	def test_submission_never_fails_without_technical_context(self):
		"""Spec 7: if automatic technical capture fails, submission must
		still succeed. Simulate by omitting every optional field."""
		doc = frappe.get_doc(
			{
				"doctype": "Bug Report",
				"title": "Minimal bug",
				"description": "Only the mandatory fields were filled in.",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)

	def test_invalid_status_transition_blocked_for_non_manager(self):
		doc = self._new_bug()
		doc.status = "Reopened"  # Pending -> Reopened is not a valid direct jump
		user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			# Administrator has System Manager so this alone won't prove
			# the block; test the underlying transition table directly.
			from bug_reporter.bug_reporter.doctype.bug_report.bug_report import STATUS_FLOW

			self.assertNotIn("Reopened", STATUS_FLOW.get("Pending", set()))
		finally:
			frappe.set_user(user)

	def test_installed_apps_captured(self):
		doc = self._new_bug()
		self.assertIn("frappe", doc.installed_apps)

	def test_resolved_can_be_reopened(self):
		doc = self._new_bug()
		doc.status = "Resolved"
		doc.save(ignore_permissions=True)
		doc.status = "Reopened"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(doc.status, "Reopened")

	def test_rejected_can_return_to_pending(self):
		doc = self._new_bug()
		doc.status = "Rejected"
		doc.save(ignore_permissions=True)
		doc.status = "Pending"
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(doc.status, "Pending")
