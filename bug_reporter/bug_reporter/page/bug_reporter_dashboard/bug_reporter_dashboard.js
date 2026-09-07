frappe.pages["bug-reporter-dashboard"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Bug Reporter Dashboard"),
		single_column: true,
	});

	page.add_inner_button(__("Open Bug Report List"), function () {
		frappe.set_route("List", "Bug Report");
	});

	var cards_wrapper = $("<div class='row bug-reporter-dashboard-cards' style='margin-top: 10px;'></div>").appendTo(page.body);

	function render(counts) {
		var items = [
			{ label: __("Pending"), value: counts.pending, filter: { status: "Pending" }, color: "#5e64ff" },
			{ label: __("Critical / High (open)"), value: counts.critical_high, filter: { severity: ["in", ["Critical", "High"]] }, color: "#e24c4c" },
			{ label: __("Reopened"), value: counts.reopened, filter: { status: "Reopened" }, color: "#f7a800" },
			{ label: __("Resolved"), value: counts.resolved, filter: { status: "Resolved" }, color: "#36b37e" },
		];

		cards_wrapper.empty();
		items.forEach(function (item) {
			var $card = $(
				"<div class='col-sm-2' style='margin-bottom: 16px;'>" +
					"<div class='bug-reporter-card' style='border-left: 4px solid " + item.color + "; padding: 12px 14px; background: var(--card-bg, #fff); border-radius: 6px; cursor: pointer; box-shadow: var(--shadow-sm, 0 1px 3px rgba(0,0,0,.08));'>" +
						"<div style='font-size: 24px; font-weight: 600;'>" + (item.value || 0) + "</div>" +
						"<div class='text-muted small'>" + item.label + "</div>" +
					"</div>" +
				"</div>"
			);
			$card.on("click", function () {
				frappe.set_route("List", "Bug Report", { ...item.filter });
			});
			cards_wrapper.append($card);
		});
	}

	frappe.call({
		method: "bug_reporter.bug_reporter.doctype.bug_report.bug_report.get_dashboard_counts",
		callback: function (r) {
			if (r && r.message) render(r.message);
		},
	});
};
