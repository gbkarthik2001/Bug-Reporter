import re
from setuptools import find_packages, setup

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

version = "0.1.0"
with open("bug_reporter/__init__.py") as f:
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
    if match:
        version = match.group(1)

setup(
    name="bug_reporter",
    version=version,
    description="In-app bug reporting with automatic technical context capture for Frappe/ERPNext (v15 & v16)",
    author="Your Organization",
    author_email="support@example.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
