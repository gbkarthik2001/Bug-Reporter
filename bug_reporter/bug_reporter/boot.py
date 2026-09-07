import frappe

from bug_reporter.utils import get_settings, user_can_submit


def extend_bootinfo(bootinfo):
	"""Push a small, non-sensitive config block into frappe.boot so the
	client-side widget can decide whether to render itself without an
	extra round trip on every page load.

	Never add secrets, tokens, or any other user's data here - bootinfo
	is sent to the browser on every session.
	"""
	try:
		settings = get_settings()
		bootinfo.bug_reporter = {
			"enabled": bool(settings.get("enabled")),
			"can_submit": user_can_submit(),
			"client_error_capture_enabled": bool(settings.get("enable_client_error_capture")),
			# Gates the fully-automatic (no click) client-error reporting in
			# bug_reporter_capture.js - independent of can_submit, which only
			# governs the manual "Report Bug" button/dialog's role check.
			"auto_client_capture_enabled": bool(settings.get("enable_auto_client_capture")),
		}
	except Exception:
		# Never break Desk boot because of this app.
		frappe.log_error(title="Bug Reporter: extend_bootinfo failed")
		bootinfo.bug_reporter = {"enabled": False, "can_submit": False}
