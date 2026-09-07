/**
 * Bug Reporter - lightweight client-side capture.
 *
 * Loaded as early as possible (first entry in app_include_js) so it can
 * observe errors/failed requests that happen anywhere on the page, even
 * before the "Report Bug" button itself has rendered.
 *
 * Privacy: only message/url/method/status/timestamp are captured. Never
 * request/response bodies, headers, cookies, or auth tokens (spec §5, §13).
 */
(function () {
	"use strict";

	if (window.__bug_reporter_capture_installed) return;
	window.__bug_reporter_capture_installed = true;

	var MAX_ERRORS = 20;
	var MAX_REQUESTS = 20;

	window.__bug_reporter_errors = window.__bug_reporter_errors || [];
	window.__bug_reporter_failed_requests = window.__bug_reporter_failed_requests || [];

	function pushCapped(arr, item, max) {
		arr.push(item);
		if (arr.length > max) arr.shift();
	}

	function safeUrl(url) {
		try {
			// Keep path + last two segments of query keys only, never values,
			// to avoid accidentally capturing tokens passed as query params.
			var u = new URL(url, window.location.origin);
			return u.origin + u.pathname;
		} catch (e) {
			return String(url).split("?")[0];
		}
	}

	// --- fully automatic reporting (no "Report Bug" click) -----------------
	// Client-side dedup only reduces chatter for a broken widget that
	// re-throws the same error repeatedly; the server independently dedupes
	// by signature + time window regardless (see auto_capture_dedup_window
	// in Bug Reporter Settings), so a full page reload can't bypass it.
	var AUTO_REPORT_DEDUP_MS = 5 * 60 * 1000;

	function autoReportDedupKey(message) {
		var hash = 0,
			str = String(message || "");
		for (var i = 0; i < str.length; i++) {
			hash = (hash << 5) - hash + str.charCodeAt(i);
			hash |= 0;
		}
		return "bug_reporter_seen_" + hash;
	}

	function shouldAutoReport(message) {
		try {
			var key = autoReportDedupKey(message);
			var last = sessionStorage.getItem(key);
			var now = Date.now();
			if (last && now - parseInt(last, 10) < AUTO_REPORT_DEDUP_MS) {
				return false;
			}
			sessionStorage.setItem(key, String(now));
			return true;
		} catch (e) {
			return true; // sessionStorage unavailable (e.g. private mode) - don't block reporting over it
		}
	}

	function sendClientErrorReport(payload) {
		window.frappe.call({
			method: "bug_reporter.api.report_client_error",
			args: { payload: JSON.stringify(payload) },
			callback: function () {},
			error: function () {},
		});
	}

	function maybeAutoReportClientError(message) {
		try {
			var f = window.frappe;
			var config = (f && f.boot && f.boot.bug_reporter) || {};
			if (!config.enabled || !config.auto_client_capture_enabled) return;
			if (!f || !f.session || f.session.user === "Guest") return;
			if (!shouldAutoReport(message)) return;

			var payload = {
				message: message,
				route: (f.get_route && f.get_route().join("/")) || window.location.pathname,
				user_agent: navigator.userAgent,
				client_errors: window.__bug_reporter_errors.slice(-5),
				failed_requests: window.__bug_reporter_failed_requests.slice(-5),
			};

			var curFrm = window.cur_frm;
			if (curFrm && curFrm.doctype && curFrm.docname) {
				payload.reference_doctype = curFrm.doctype;
				payload.reference_name = curFrm.docname;
			}

			sendClientErrorReport(payload);
		} catch (e) {
			/* auto-reporting must never itself throw */
		}
	}

	window.addEventListener("error", function (event) {
		try {
			var message = (event.message || "Unknown error").slice(0, 500);
			pushCapped(
				window.__bug_reporter_errors,
				{
					message: message,
					source: event.filename ? safeUrl(event.filename) : "",
					line: event.lineno,
					col: event.colno,
					time: new Date().toISOString(),
				},
				MAX_ERRORS
			);
			maybeAutoReportClientError(message);
		} catch (e) {
			/* never let the capture layer itself throw */
		}
	});

	window.addEventListener("unhandledrejection", function (event) {
		try {
			var reason = event.reason;
			var message = ("Unhandled promise rejection: " + (reason && reason.message ? reason.message : String(reason))).slice(
				0,
				500
			);
			pushCapped(
				window.__bug_reporter_errors,
				{
					message: message,
					time: new Date().toISOString(),
				},
				MAX_ERRORS
			);
			maybeAutoReportClientError(message);
		} catch (e) {
			/* noop */
		}
	});

	// --- fetch() ---------------------------------------------------------
	if (window.fetch) {
		var originalFetch = window.fetch;
		window.fetch = function () {
			var args = arguments;
			var url = args[0] && args[0].url ? args[0].url : args[0];
			var method = (args[1] && args[1].method) || "GET";
			return originalFetch.apply(this, args).then(
				function (response) {
					try {
						if (!response.ok) {
							pushCapped(
								window.__bug_reporter_failed_requests,
								{
									url: safeUrl(url),
									method: method,
									status: response.status,
									time: new Date().toISOString(),
								},
								MAX_REQUESTS
							);
						}
					} catch (e) {
						/* noop */
					}
					return response;
				},
				function (err) {
					try {
						pushCapped(
							window.__bug_reporter_failed_requests,
							{
								url: safeUrl(url),
								method: method,
								status: "network_error",
								time: new Date().toISOString(),
							},
							MAX_REQUESTS
						);
					} catch (e) {
						/* noop */
					}
					throw err;
				}
			);
		};
	}

	// --- XMLHttpRequest ----------------------------------------------------
	if (window.XMLHttpRequest) {
		var originalOpen = XMLHttpRequest.prototype.open;
		XMLHttpRequest.prototype.open = function (method, url) {
			this.__bug_reporter_method = method;
			this.__bug_reporter_url = url;
			return originalOpen.apply(this, arguments);
		};

		var originalSend = XMLHttpRequest.prototype.send;
		XMLHttpRequest.prototype.send = function () {
			var xhr = this;
			xhr.addEventListener("loadend", function () {
				try {
					if (xhr.status === 0 || xhr.status >= 400) {
						pushCapped(
							window.__bug_reporter_failed_requests,
							{
								url: safeUrl(xhr.__bug_reporter_url || ""),
								method: xhr.__bug_reporter_method || "GET",
								status: xhr.status,
								time: new Date().toISOString(),
							},
							MAX_REQUESTS
						);
					}
				} catch (e) {
					/* noop */
				}
			});
			return originalSend.apply(this, arguments);
		};
	}
})();
