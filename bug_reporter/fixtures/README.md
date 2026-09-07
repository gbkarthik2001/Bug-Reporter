This folder is populated automatically when an administrator runs:

    bench --site <site> export-fixtures --app bug_reporter

The `fixtures` list in `hooks.py` currently exports the
`Bug Reporter Tester` and `Bug Reporter Manager` roles, so they can be
version-controlled and reproduced identically across dev/staging/prod
sites. The roles are also created automatically on install via
`install.after_install`, so running export-fixtures is optional and only
useful if you customize the roles (e.g. rename them, change
`desk_access`) and want that customization to ship with the app.
