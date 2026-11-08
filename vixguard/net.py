"""Minimal HTTP JSON helpers built on urllib. No third-party packages."""

from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Mapping, Optional

DEFAULT_TIMEOUT = 15.0
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class NetworkError(RuntimeError):
    """Any transport-level failure while calling a remote endpoint."""


def _host(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).netloc or "remote host"
    except ValueError:
        return "remote host"


def _decode(body: bytes, encoding: Optional[str]) -> str:
    if encoding and "gzip" in encoding.lower():
        try:
            body = gzip.decompress(body)
        except OSError:
            pass
    return body.decode("utf-8", "replace")


def _request(
    url: str,
    *,
    data: Optional[bytes] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    request = urllib.request.Request(url, data=data, headers=dict(headers or {}))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _decode(response.read(), response.headers.get("Content-Encoding"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        suffix = f": {detail}" if detail else ""
        raise NetworkError(f"HTTP {exc.code} from {_host(url)}{suffix}") from None
    except urllib.error.URLError as exc:
        raise NetworkError(f"{_host(url)} unreachable: {exc.reason}") from None
    except Exception as exc:  # socket timeouts, TLS errors, ...
        raise NetworkError(f"{_host(url)} request failed: {exc}") from None


def get_json(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """GET a URL and decode a JSON response."""
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}{'&' if '?' in url else '?'}{query}"
    merged = {"Accept": "application/json, text/plain, */*", "User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    body = _request(url, headers=merged, timeout=timeout)
    try:
        return json.loads(body)
    except ValueError:
        raise NetworkError(f"{_host(url)} returned invalid JSON") from None
