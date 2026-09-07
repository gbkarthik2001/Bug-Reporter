# Copyright (c) 2026, Your Organization
# License: MIT

import frappe
from frappe.model.document import Document


class BugReporterSettings(Document):
	def validate(self):
		if self.error_log_correlation_window_minutes and self.error_log_correlation_window_minutes < 0:
			frappe.throw("Error Log Correlation Window cannot be negative.")
		self._validate_default_matches_bug_report_options("default_severity", "severity")
		self._validate_default_matches_bug_report_options("default_priority", "priority")

	def _validate_default_matches_bug_report_options(self, own_fieldname, bug_report_fieldname):
		"""Bug Report's own Severity/Priority fields are the single source
		of truth for these choices (see bug_reporter_settings.js, which
		mirrors the same options into the form at runtime) - this is the
		authoritative, non-bypassable check for whatever actually gets
		saved, including via API/import, not just what the loaded form
		happened to render."""
		value = self.get(own_fieldname)
		if not value:
			return
		options = (frappe.get_meta("Bug Report").get_field(bug_report_fieldname).options or "").split("\n")
		if value not in options:
			frappe.throw(
				frappe._("{0} must be one of Bug Report's own {1} options: {2}").format(
					self.meta.get_label(own_fieldname), bug_report_fieldname.title(), ", ".join(options)
				)
			)
