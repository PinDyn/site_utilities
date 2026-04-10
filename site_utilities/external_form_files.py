"""Helpers for External Form Submission server scripts (binary downloads not possible in safe_exec)."""

import mimetypes
import os
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import cint, get_request_session
from frappe.utils.file_manager import save_file

# SSRF mitigation: extend via site_config external_form_download_allowed_host_suffixes (list or string).
_DEFAULT_ALLOWED_HOST_SUFFIXES = (
	"amazonaws.com",
	"amazoncognito.com",
	"cloudfront.net",
	"on.aws",  # some AWS object URLs use *.on.aws
	"cognitoforms.com",  # Cognito Forms (non-AWS) file CDN
	"ctfassets.net",  # Cognito Forms assets
)


def _hostname_from_url(url: str) -> str | None:
	try:
		parsed = urlparse((url or "").strip())
	except Exception:
		return None
	if parsed.scheme not in ("http", "https"):
		return None
	host = parsed.hostname
	if not host:
		return None
	return host.lower()


def _download_host_allowed(hostname: str) -> bool:
	extra = frappe.conf.get("external_form_download_allowed_host_suffixes") or []
	if isinstance(extra, str):
		extra = [extra]
	for suffix in tuple(_DEFAULT_ALLOWED_HOST_SUFFIXES) + tuple(extra):
		s = str(suffix).lower().lstrip(".")
		if hostname == s or hostname.endswith("." + s):
			return True
	return False


@frappe.whitelist()
def download_external_upload_and_attach(
	file_url,
	file_name=None,
	attached_to_doctype=None,
	attached_to_name=None,
	is_private=1,
	folder=None,
):
	"""GET ``file_url`` as bytes and attach via ``save_file`` (presigned URLs, etc.)."""
	if not file_url or not attached_to_doctype or not attached_to_name:
		frappe.throw(_("file_url, attached_to_doctype and attached_to_name are required"))

	hostname = _hostname_from_url(file_url)
	if not hostname:
		frappe.throw(_("Download URL is missing or invalid (could not parse hostname)"))
	if not _download_host_allowed(hostname):
		frappe.throw(
			_(
				"Download URL host {0} is not allowed. "
				"Set site_config key external_form_download_allowed_host_suffixes to include its domain "
				"(e.g. [\"yourcdn.example.com\"])."
			).format(hostname)
		)

	name = (file_name or "attachment").strip() or "attachment"
	name = os.path.basename(name)

	session = get_request_session()
	resp = session.get(file_url, timeout=120)
	resp.raise_for_status()
	content = resp.content
	if not content:
		frappe.throw(_("Empty file body"))

	ct = (resp.headers.get("content-type") or "").split(";")[0].strip()
	if ct and not os.path.splitext(name)[1]:
		ext = mimetypes.guess_extension(ct)
		if ext == ".jpe":
			ext = ".jpg"
		if ext:
			name = name + ext

	priv = cint(is_private)
	folder = folder or "Home/Attachments"

	return save_file(name, content, attached_to_doctype, attached_to_name, folder=folder, is_private=priv)
