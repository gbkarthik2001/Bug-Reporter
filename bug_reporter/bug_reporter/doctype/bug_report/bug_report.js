// Copyright (c) 2026, Your Organization
// License: MIT

frappe.ui.form.on("Bug Report", {
	refresh(frm) {
		if (frm.doc.error_log) {
			frm.add_custom_button(__("View Related Error Log"), () => {
				frappe.set_route("Form", "Error Log", frm.doc.error_log);
			});
		}

		if (!frm.is_new() && frm.doc.reference_doctype && frm.doc.reference_name) {
			frm.add_custom_button(__("Open Source Document"), () => {
				frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name);
			});
		}

		if (frm.doc.redmine_issue_url) {
			frm.add_custom_button(__("Open in Redmine"), () => {
				window.open(frm.doc.redmine_issue_url, "_blank");
			});
		}

		if (!frm.is_new()) {
			frm.add_custom_button(
				frm.doc.redmine_issue_id ? __("Sync to Redmine") : __("Create in Redmine"),
				() => frm.trigger("sync_to_redmine")
			);
		}

		if (!frm.is_new()) {
			frm.dashboard.add_indicator(
				__("Bug ID: {0}", [frm.doc.name]),
				"blue"
			);
		}

		frm.trigger("render_technical_context");
	},

	sync_to_redmine(frm) {
		frappe.call({
			method: "bug_reporter.redmine.manual_sync_to_redmine",
			args: { bug_report_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Syncing to Redmine..."),
			callback(r) {
				if (!r.message) return;
				frappe.show_alert({
					message: r.message.created
						? __("Redmine issue #{0} created.", [r.message.issue_id])
						: __("Redmine issue #{0} updated.", [r.message.issue_id]),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	},

	render_technical_context(frm) {
		try {
			const errors = frm.doc.client_errors ? JSON.parse(frm.doc.client_errors) : [];
			if (errors.length && frm.fields_dict.error_section) {
				let html = "<div class='text-muted small'><b>" + __("Client-side errors captured near submission:") + "</b><ul>";
				errors.slice(0, 5).forEach((e) => {
					html += `<li>${frappe.utils.escape_html(e.message || "")} <span class='text-muted'>(${frappe.utils.escape_html(e.time || "")})</span></li>`;
				});
				html += "</ul></div>";
				frm.get_field("error_section").$wrapper.find(".bug-reporter-context-preview").remove();
				$(html).addClass("bug-reporter-context-preview").insertBefore(
					frm.get_field("client_errors").$wrapper
				);
			}
		} catch (e) {
			// Non-critical rendering helper only - never block the form.
		}
	},
});
