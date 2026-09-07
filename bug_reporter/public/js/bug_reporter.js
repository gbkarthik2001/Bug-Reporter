/**
 * Bug Reporter - "Report Bug" floating action button + dialog.
 *
 * Renders only inside the Frappe Desk (frappe.ready), never on public
 * website pages, and only for users who are allowed to submit reports
 * (server-checked via frappe.boot.bug_reporter, itself re-verified by
 * the server on every submit call - see bug_reporter/api.py).
 */
(function () {
	"use strict";

	if (typeof frappe === "undefined" || !frappe.ready) return;

	frappe.ready(function () {
		var config = (frappe.boot && frappe.boot.bug_reporter) || {};
		if (!config.enabled || !config.can_submit) return;
		if (document.getElementById("bug-reporter-fab")) return;

		renderButton(config);
	});

	function renderButton(config) {
		var btn = document.createElement("button");
		btn.id = "bug-reporter-fab";
		btn.type = "button";
		btn.className = "bug-reporter-fab";
		btn.setAttribute("aria-label", __("Report a bug"));
		btn.setAttribute("title", __("Report Bug"));
		btn.innerHTML =
			'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
			'<path d="M8 3h8M12 3v4M9 8h6a4 4 0 014 4v4a4 4 0 01-4 4h-2 M9 8H7a4 4 0 00-4 4v4a4 4 0 004 4h2M9 8v12M15 8v12M4 12h2m12 0h2M4 16h2m12 0h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
			'<span class="bug-reporter-fab-label">' + __("Report Bug") + "</span>";

		btn.addEventListener("click", function () {
			openBugReportDialog(config);
		});

		document.body.appendChild(btn);
	}

	function getCurrentContext() {
		var route = "";
		try {
			route = frappe.get_route_str ? frappe.get_route_str() : window.location.hash.replace("#", "");
		} catch (e) {
			route = window.location.pathname + window.location.hash;
		}

		var reference_doctype = "";
		var reference_name = "";
		try {
			if (window.cur_frm && cur_frm.doc && cur_frm.doc.doctype) {
				reference_doctype = cur_frm.doc.doctype;
				reference_name = cur_frm.doc.name;
			} else if (window.cur_list && cur_list.doctype) {
				reference_doctype = cur_list.doctype;
			}
		} catch (e) {
			/* best effort only */
		}

		return {
			route: route,
			reference_doctype: reference_doctype,
			reference_name: reference_name,
			user_agent: navigator.userAgent || "",
		};
	}

	function generateCorrelationId() {
		try {
			return (frappe.utils && frappe.utils.get_random) ? frappe.utils.get_random(10) : Math.random().toString(36).slice(2, 12);
		} catch (e) {
			return Math.random().toString(36).slice(2, 12);
		}
	}

	function openBugReportDialog(config) {
		var context = getCurrentContext();
		var correlationId = generateCorrelationId();
		var recentErrors = (window.__bug_reporter_errors || []).slice(-5);
		var recentFailedRequests = (window.__bug_reporter_failed_requests || []).slice(-5);

		var technicalHtml =
			"<div class='bug-reporter-technical text-muted small'>" +
			"<div><b>" + __("Route") + ":</b> " + frappe.utils.escape_html(context.route || "-") + "</div>" +
			(context.reference_doctype
				? "<div><b>" + __("DocType") + ":</b> " + frappe.utils.escape_html(context.reference_doctype) +
				  (context.reference_name ? " / " + frappe.utils.escape_html(context.reference_name) : "") + "</div>"
				: "") +
			"<div><b>" + __("Correlation ID") + ":</b> " + correlationId + "</div>" +
			(recentErrors.length
				? "<div style='margin-top:6px'><b>" + __("Recently detected errors") + ":</b><ul style='margin:2px 0 0 16px;padding:0'>" +
				  recentErrors.map(function (e) {
					  return "<li>" + frappe.utils.escape_html(e.message || "") + "</li>";
				  }).join("") + "</ul></div>"
				: "") +
			(recentFailedRequests.length
				? "<div style='margin-top:6px'><b>" + __("Recently failed requests") + ":</b><ul style='margin:2px 0 0 16px;padding:0'>" +
				  recentFailedRequests.map(function (r) {
					  return "<li>" + r.method + " " + frappe.utils.escape_html(r.url) + " → " + r.status + "</li>";
				  }).join("") + "</ul></div>"
				: "") +
			"</div>";

		var fields = [
			{
				fieldname: "title",
				fieldtype: "Data",
				label: __("Title"),
				reqd: 1,
			},
			{
				fieldname: "description",
				fieldtype: "Small Text",
				label: __("What happened?"),
				reqd: 1,
			},
			{ fieldname: "col_break_1", fieldtype: "Column Break" },
			{
				fieldname: "expected_result",
				fieldtype: "Small Text",
				label: __("Expected Result"),
			},
			{
				fieldname: "actual_result",
				fieldtype: "Small Text",
				label: __("Actual Result"),
			},
			{ fieldname: "sec_break_1", fieldtype: "Section Break" },
			{
				fieldname: "severity",
				fieldtype: "Select",
				label: __("Severity"),
				options: config.severity_options,
				default: config.default_severity,
			},
			{
				fieldname: "priority",
				fieldtype: "Select",
				label: __("Priority"),
				options: config.priority_options,
				default: config.default_priority,
			},
			{ fieldname: "col_break_2", fieldtype: "Column Break" },
			{
				fieldname: "screenshot",
				fieldtype: "Attach",
				label: __("Screenshot"),
			},
		];

		if (config.client_error_capture_enabled && (recentErrors.length || recentFailedRequests.length)) {
			fields.push({
				fieldname: "error_message",
				fieldtype: "Small Text",
				label: __("Error text (edit/confirm if relevant)"),
				default: recentErrors.length ? recentErrors[recentErrors.length - 1].message : "",
			});
		}

		fields.push(
			{ fieldname: "tech_section", fieldtype: "Section Break", label: __("Technical Details"), collapsible: 1 },
			{ fieldname: "steps_to_reproduce", fieldtype: "Small Text", label: __("Steps to Reproduce (optional)") },
			{ fieldname: "technical_html", fieldtype: "HTML", options: technicalHtml }
		);

		var dialog = new frappe.ui.Dialog({
			title: __("Report Bug"),
			fields: fields,
			size: "large",
			primary_action_label: __("Submit"),
			primary_action: function (values) {
				dialog.get_primary_btn().prop("disabled", true).text(__("Submitting..."));

				var payload = {
					title: values.title,
					description: values.description,
					expected_result: values.expected_result,
					actual_result: values.actual_result,
					steps_to_reproduce: values.steps_to_reproduce,
					severity: values.severity,
					priority: values.priority,
					screenshot: values.screenshot,
					error_message: values.error_message || (recentErrors.length ? recentErrors[recentErrors.length - 1].message : ""),
					route: context.route,
					reference_doctype: context.reference_doctype,
					reference_name: context.reference_name,
					user_agent: context.user_agent,
					correlation_id: correlationId,
					client_errors: recentErrors,
					failed_requests: recentFailedRequests,
				};

				frappe.call({
					method: "bug_reporter.api.submit_bug_report",
					args: { payload: JSON.stringify(payload) },
					callback: function (r) {
						dialog.hide();
						if (r && r.message && r.message.name) {
							showSuccess(r.message.name);
						} else {
							frappe.show_alert({ message: __("Bug report submitted."), indicator: "green" });
						}
					},
					error: function () {
						dialog.get_primary_btn().prop("disabled", false).text(__("Submit"));
					},
					always: function () {
						dialog.get_primary_btn().prop("disabled", false).text(__("Submit"));
					},
				});
			},
		});

		dialog.show();
	}

	function showSuccess(bugId) {
		var wrapper = $(
			"<div>" +
				"<p>" + __("Thank you - your bug report was submitted.") + "</p>" +
				"<p><b>" + __("Bug ID") + ":</b> <code id='bug-reporter-new-id'>" + frappe.utils.escape_html(bugId) + "</code> " +
				"<button class='btn btn-xs btn-default' id='bug-reporter-copy-id'>" + __("Copy") + "</button></p>" +
			"</div>"
		);

		var d = frappe.msgprint({
			message: wrapper,
			title: __("Bug Reported"),
			indicator: "green",
		});

		wrapper.find("#bug-reporter-copy-id").on("click", function () {
			navigator.clipboard && navigator.clipboard.writeText(bugId);
			frappe.show_alert({ message: __("Copied"), indicator: "blue" });
		});

		if (d && d.footer) {
			$("<button class='btn btn-sm btn-primary'>" + __("Open Bug Report") + "</button>")
				.appendTo(d.footer)
				.on("click", function () {
					d.hide();
					frappe.set_route("Form", "Bug Report", bugId);
				});
		}
	}
})();
