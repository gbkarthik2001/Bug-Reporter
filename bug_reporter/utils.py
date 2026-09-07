"""
Shared helpers for Bug Reporter.

Everything that touches an *optional* dependency (ERPNext, another
installed app) or a Frappe API surface that could plausibly differ
between v15 and v16 lives here, behind a defensive try/except, so the
rest of the codebase can call a single stable function instead of
sprinkling version checks everywhere.
"""

import hashlib
import json
import re
from urllib.parse import urlparse

import frappe
from frappe.utils import add_to_date, cint, now_datetime

_REQUEST_URL_RE = re.compile(r"Request '([^']+)'")
_APP_ROUTE_RE = re.compile(r"^/app/([a-z0-9-]+)(?:/([^/?]+))?")
_DOCTYPE_MODULE_RE = re.compile(r"\.doctype\.([a-zA-Z0-9_]+)\.")

SETTINGS_DOCTYPE = "Bug Reporter Settings"

DEFAULT_SETTINGS = {
	"enabled": 1,
	"enable_client_error_capture": 1,
	"enable_error_log_association": 1,
	"auto_create_issue": 0,
	"default_severity": "Medium",
	"default_priority": "Medium",
	"error_log_correlation_window_minutes": 10,
	"retention_days": 0,
	"enable_auto_server_capture": 1,
	"enable_auto_client_capture": 1,
	"auto_capture_dedup_window_minutes": 30,
	"enable_redmine_sync": 0,
	"redmine_tracker_id": 1,
}


def get_frappe_version():
	"""Return the running Frappe major version as an int (15, 16, ...).

	Falls back to 0 if it genuinely cannot be determined - callers must
	treat that as "unknown, assume modern API".
	"""
	try:
		return cint(frappe.__version__.split(".")[0])
	except Exception:
		return 0


def get_settings():
	"""Return Bug Reporter Settings as a plain dict, seeded with safe
	defaults for any field that has not been configured yet (e.g. right
	after install, before the Single doc has been saved once)."""
	try:
		doc = frappe.get_cached_doc(SETTINGS_DOCTYPE)
		data = doc.as_dict()
	except Exception:
		data = {}

	merged = dict(DEFAULT_SETTINGS)
	for key, value in data.items():
		if value not in (None, ""):
			merged[key] = value
	return merged


def get_allowed_roles():
	"""Roles permitted to submit a bug report, from settings' child table.
	Defaults to anyone holding the built-in 'Bug Reporter Tester' role."""
	roles = set()
	try:
		doc = frappe.get_cached_doc(SETTINGS_DOCTYPE)
		for row in getattr(doc, "allowed_roles", []) or []:
			role = getattr(row, "role", None)
			if role:
				roles.add(role)
	except Exception:
		pass
	if not roles:
		roles = {"Bug Reporter Tester", "Bug Reporter Manager", "System Manager"}
	return roles


def user_can_submit(user=None):
	user = user or frappe.session.user
	if user == "Guest":
		return False
	if "System Manager" in frappe.get_roles(user):
		return True
	settings = get_settings()
	if not cint(settings.get("enabled")):
		return False
	allowed = get_allowed_roles()
	user_roles = set(frappe.get_roles(user))
	return bool(allowed & user_roles)


def user_is_manager(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	return bool(roles & {"Bug Reporter Manager", "System Manager"})


def safe_get_default_company(user=None):
	"""Best-effort company lookup that never assumes ERPNext (or any
	other app defining 'Company') is installed. Returns a plain string,
	never a broken Link, so Bug Report has zero hard dependency on
	ERPNext being present on the site."""
	user = user or frappe.session.user
	try:
		if not frappe.db.exists("DocType", "Company"):
			return None
		company = frappe.defaults.get_user_default("Company", user) or frappe.defaults.get_global_default(
			"Company"
		)
		return company
	except Exception:
		return None


def get_installed_apps_summary():
	"""Comma separated list of installed apps + their versions, purely
	for diagnostic context on the bug report - never used to gate logic,
	so a missing/renamed app never breaks submission."""
	try:
		apps = frappe.get_installed_apps()
		parts = []
		for app in apps:
			try:
				version = frappe.get_attr(f"{app}.__version__")
			except Exception:
				version = ""
			parts.append(f"{app}=={version}" if version else app)
		return ", ".join(parts)
	except Exception:
		return ""


def parse_user_agent(user_agent):
	"""Very small, dependency-free UA parser. Good enough for support
	triage; not meant to be exhaustive. Never raises."""
	browser, os_name = "Unknown", "Unknown"
	try:
		ua = (user_agent or "").lower()
		if "edg/" in ua:
			browser = "Edge"
		elif "chrome/" in ua and "chromium" not in ua:
			browser = "Chrome"
		elif "firefox/" in ua:
			browser = "Firefox"
		elif "safari/" in ua and "chrome/" not in ua:
			browser = "Safari"
		elif "opr/" in ua or "opera" in ua:
			browser = "Opera"

		if "windows" in ua:
			os_name = "Windows"
		elif "mac os" in ua or "macintosh" in ua:
			os_name = "macOS"
		elif "android" in ua:
			os_name = "Android"
		elif "iphone" in ua or "ipad" in ua:
			os_name = "iOS"
		elif "linux" in ua:
			os_name = "Linux"
	except Exception:
		pass
	return browser, os_name


def find_candidate_error_logs(reference_time=None, window_minutes=None):
	"""Best-effort correlation with server-side Error Log entries.

	Frappe's core Error Log doctype does not reliably store the acting
	user across versions, so we correlate on time proximity only and
	return a short list of candidates for a human to confirm rather than
	silently auto-assigning a possibly-wrong log. Never raises - a
	correlation failure must never block bug submission (spec section 7).
	"""
	try:
		settings = get_settings()
		window_minutes = cint(window_minutes or settings.get("error_log_correlation_window_minutes") or 10)
		reference_time = reference_time or now_datetime()
		start = frappe.utils.add_to_date(reference_time, minutes=-window_minutes)
		end = frappe.utils.add_to_date(reference_time, minutes=1)

		rows = frappe.get_all(
			"Error Log",
			filters=[["creation", ">=", start], ["creation", "<=", end]],
			fields=["name", "method", "creation"],
			order_by="creation desc",
			limit_page_length=5,
		)
		return rows
	except Exception:
		frappe.log_error(title="Bug Reporter: error log correlation failed")
		return []


def log_client_error_to_error_log(correlation_id, message):
	"""Optionally mirror a client-side error into Frappe's own Error Log
	so it shows up alongside server errors for the same correlation id,
	making later log searches ("grep the correlation id") work
	regardless of whether the error originated client- or server-side.
	"""
	try:
		frappe.log_error(
			title=f"Bug Reporter Client Error [{correlation_id}]",
			message=message,
		)
	except Exception:
		pass


def safe_json_loads(value, default=None):
	if not value:
		return default
	try:
		return json.loads(value)
	except Exception:
		return default


def truncate(value, length=140):
	if not value:
		return value
	value = str(value)
	return value if len(value) <= length else value[: length - 1] + "…"


def build_auto_capture_signature(source, key):
	"""Deterministic, short identifier for an auto-captured error, stored in
	Bug Report.correlation_id so repeats of the *same* error can be detected
	(see was_recently_auto_captured) instead of creating/emailing a fresh
	Bug Report every single time it recurs."""
	basis = f"{source}:{(key or '').strip()[:300]}"
	return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:20]


def was_recently_auto_captured(signature, window_minutes=None):
	"""True if an auto-captured Bug Report with this exact signature was
	already created within the dedup window - the caller should skip
	creating (and emailing about) another one. Never raises: a lookup
	failure must default to "not a duplicate" rather than silently
	swallowing a genuine new error."""
	try:
		settings = get_settings()
		window_minutes = cint(window_minutes or settings.get("auto_capture_dedup_window_minutes") or 30)
		cutoff = add_to_date(now_datetime(), minutes=-window_minutes)
		return bool(
			frappe.db.exists(
				"Bug Report",
				{
					"correlation_id": signature,
					"auto_captured": 1,
					"creation": [">=", cutoff],
				},
			)
		)
	except Exception:
		frappe.log_error(title="Bug Reporter: auto-capture dedup check failed")
		return False


def _build_doctype_lookup_maps():
	"""route-slug -> DocType name, and module-folder-scrub -> DocType name,
	both computed fresh from frappe.get_all("DocType") each call (crashes
	are rare enough that this isn't worth caching/risking staleness).
	route-slug matches frappe.router.slug() in the desk JS (lowercase,
	spaces -> dashes); module-folder-scrub matches frappe.scrub() (lowercase,
	spaces -> underscores), which is how every doctype's own controller
	module is named on disk (<app>/<module>/doctype/<scrub>/<scrub>.py)."""
	try:
		names = frappe.get_all("DocType", pluck="name")
	except Exception:
		return {}, {}
	slug_map, scrub_map = {}, {}
	for name in names:
		slug_map[name.lower().replace(" ", "-")] = name
		scrub_map[frappe.scrub(name)] = name
	return slug_map, scrub_map


def extract_context_from_traceback(traceback_text):
	"""Best-effort (route, reference_doctype, reference_name) recovered
	from a Frappe traceback's own captured request URL. Needed because
	Frappe's own crash logging (log_error_snapshot, see auto_capture.py)
	never records reference_doctype/reference_name on the Error Log at
	all - there's nothing to read off the Error Log itself, so this parses
	the "Request '<url>'" line every "Traceback with variables" capture
	includes. Never raises - returns (None, None, None) on any failure,
	including on a plain (non-verbose) traceback with no such line.
	"""
	try:
		if not traceback_text:
			return None, None, None

		match = _REQUEST_URL_RE.search(traceback_text)
		if not match:
			return None, None, None

		path = urlparse(match.group(1)).path
		if not path:
			return None, None, None

		slug_map, scrub_map = _build_doctype_lookup_maps()

		# A normal desk form view: /app/<doctype-slug>/<docname>
		app_match = _APP_ROUTE_RE.match(path)
		if app_match:
			doctype = slug_map.get(app_match.group(1))
			docname = app_match.group(2)
			return path, doctype, (docname if doctype else None)

		# A whitelisted method call: /api/method/<app>.<module>.doctype.<x>.<x>.<fn>
		doctype_module_match = _DOCTYPE_MODULE_RE.search(path)
		if doctype_module_match:
			doctype = scrub_map.get(doctype_module_match.group(1))
			if doctype:
				return path, doctype, None

		return path, None, None
	except Exception:
		return None, None, None
