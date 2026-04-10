"""Helpers for External Form Submission server scripts (binary downloads not possible in safe_exec)."""

import mimetypes
import os
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import cint, get_request_session
from frappe.utils.file_manager import save_file

# SSRF mitigation: Cognito file links are usually S3 / CloudFront. Extend via site_config if needed.
_DEFAULT_ALLOWED_HOST_SUFFIXES = (
	"amazonaws.com",
	"amazoncognito.com",
	"cloudfront.net",
)


def _download_host_allowed(url: str) -> bool:
	try:
		parsed = urlparse((url or "").strip())
	except Exception:
		return False
	host = (parsed.netloc or "").lower()
	if not host or parsed.scheme not in ("http", "https"):
		return False
	extra = frappe.conf.get("external_form_download_allowed_host_suffixes") or []
	if isinstance(extra, str):
		extra = [extra]
	for suffix in tuple(_DEFAULT_ALLOWED_HOST_SUFFIXES) + tuple(extra):
		s = str(suffix).lower().lstrip(".")
		if host == s or host.endswith("." + s):
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

	if not _download_host_allowed(file_url):
		frappe.throw(_("Download URL host is not allowed"))

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
