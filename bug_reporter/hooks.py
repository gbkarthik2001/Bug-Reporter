from . import __version__ as app_version

app_name = "bug_reporter"
app_title = "Bug Reporter"
app_publisher = "Your Organization"
app_description = "In-app bug reporting with automatic technical context capture for Frappe/ERPNext"
app_email = "support@example.com"
app_license = "MIT"
app_version = app_version

# Frappe v15 / v16 compatibility
# ---------------------------------------------------------------
# This app intentionally avoids version-pinned or unstable APIs.
# `required_apps` is left empty because the app only depends on the
# `frappe` framework itself (present in both v15 and v16). Any optional
# integration with ERPNext or other installed apps is feature-detected
# at runtime in bug_reporter/utils.py (see `safe_get_default_company`,
# `get_installed_apps_summary`, etc.) rather than declared as a hard
# dependency, so the app installs cleanly on sites with or without
# ERPNext or any other combination of installed apps.
required_apps = []

# Includes in <head>
# ------------------
app_include_js = [
    "/assets/bug_reporter/js/bug_reporter_capture.js",
    "/assets/bug_reporter/js/bug_reporter.js",
]
app_include_css = [
    "/assets/bug_reporter/css/bug_reporter.css",
]

# Boot session
# ------------
# Pushes a small, non-sensitive config block to every Desk session so the
# client-side button can decide whether to render without an extra
# round-trip. Never put secrets in bootinfo - it is visible to the browser.
extend_bootinfo = "bug_reporter.bug_reporter.boot.extend_bootinfo"

# Doc Events
# ----------
doc_events = {
    "Bug Report": {
        "before_insert": "bug_reporter.bug_reporter.doctype.bug_report.bug_report.before_insert",
        "after_insert": "bug_reporter.bug_reporter.doctype.bug_report.bug_report.after_insert",
        "on_update": "bug_reporter.bug_reporter.doctype.bug_report.bug_report.on_update",
    },
    # Fully automatic server-side capture - no "Report Bug" click involved.
    # Frappe only writes to its own core Error Log for genuine unhandled
    # crashes (http_status_code >= 500) or an app's own explicit
    # frappe.log_error() call on something it caught; routine
    # frappe.throw() validation/permission errors never reach it. See
    # bug_reporter/auto_capture.py for the full reasoning.
    "Error Log": {
        "after_insert": "bug_reporter.auto_capture.capture_server_error",
    },
}

# Scheduled Tasks
# ---------------
scheduler_events = {
    "daily": [
        "bug_reporter.tasks.cleanup_old_evidence",
    ],
    "weekly": [
        "bug_reporter.tasks.send_weekly_pending_summary",
    ],
    "cron": {
        # Pull Redmine issue statuses for open Bug Reports every 15 minutes
        # and auto-resolve here when they hit the configured trigger status
        # (e.g. "Deployed to UAT") - see redmine.pull_status_updates.
        "*/15 * * * *": [
            "bug_reporter.redmine.pull_status_updates",
        ],
    },
}

# Installation
# ------------
after_install = "bug_reporter.install.after_install"
before_uninstall = "bug_reporter.install.before_uninstall"

# Fixtures
# --------
# Exported/imported on `bench migrate` so roles ship with the app instead
# of requiring manual setup on every site.
fixtures = [
    {
        "dt": "Role",
        "filters": [["name", "in", ["Bug Reporter Tester", "Bug Reporter Manager"]]],
    },
]

# Whitelisted / API methods are defined directly in bug_reporter/api.py
# using the @frappe.whitelist() decorator - no additional hook wiring
# is required for them.
