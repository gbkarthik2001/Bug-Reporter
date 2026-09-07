// Copyright (c) 2026, Your Organization
// License: MIT

frappe.ui.form.on("Bug Reporter Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open Bug Reporter List"), () => {
			frappe.set_route("List", "Bug Report");
		});
		frm.trigger("sync_severity_priority_options");
	},

	// Default Severity/Priority must always offer exactly the same choices
	// as Bug Report's own Severity/Priority fields - sourced from there at
	// runtime rather than duplicating the option list in this doctype's
	// JSON, so adding/renaming a severity or priority level on Bug Report
	// can never silently drift out of sync with what's selectable here.
	sync_severity_priority_options(frm) {
		frappe.model.with_doctype("Bug Report", () => {
			const meta = frappe.get_meta("Bug Report");
			const severity_field = meta && meta.fields.find((f) => f.fieldname === "severity");
			const priority_field = meta && meta.fields.find((f) => f.fieldname === "priority");

			if (severity_field) {
				frm.set_df_property("default_severity", "options", severity_field.options);
				frm.refresh_field("default_severity");
			}
			if (priority_field) {
				frm.set_df_property("default_priority", "options", priority_field.options);
				frm.refresh_field("default_priority");
			}
		});
	},
});
