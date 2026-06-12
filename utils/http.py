"""
HTTPユーティリティ — requests.Session + tenacity 再試行

依存: requests, tenacity

使い方:
from utils.http import HTTPClient
client = HTTPClient()
text = client.get_text(url)
json = client.get_json(url)
"""
from __future__ import annotations

import requests
from requests import Response
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Any, Optional


class HTTPError(Exception):
    pass


class HTTPClient:
    def __init__(self, timeout: int = 10):
        self.session = requests.Session()
        self.timeout = timeout

    def _raise_for_status(self, resp: Response) -> None:
        try:
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HTTPError(str(e)) from e

    @retry(reraise=True, stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5, max=30),
            retry=retry_if_exception_type(requests.RequestException))
    def _get(self, url: str, **kwargs) -> Response:
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        if resp.status_code >= 400:
            # raise requests HTTPError to trigger retry
            resp.raise_for_status()
        return resp

    def get_text(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> str:
        try:
            resp = self._get(url, params=params, headers=headers)
            return resp.text
        except Exception as e:
            raise HTTPError(f"Failed to GET {url}: {e}") from e

    def get_json(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
        try:
            resp = self._get(url, params=params, headers=headers)
            return resp.json()
        except ValueError as e:
            raise HTTPError(f"Invalid JSON from {url}: {e}") from e
        except Exception as e:
            raise HTTPError(f"Failed to GET JSON {url}: {e}") from e

    @retry(reraise=True, stop=stop_after_attempt(5), wait=wait_exponential(multiplier=0.5, max=30),
            retry=retry_if_exception_type(requests.RequestException))
    def post_json(self, url: str, payload: Any, headers: Optional[dict] = None) -> Any:
        try:
            resp = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            if resp.status_code >= 400:
                resp.raise_for_status()
            return resp.json() if resp.text else {}
        except Exception as e:
            raise HTTPError(f"Failed to POST {url}: {e}") from e


# simple module-level client for convenience
_default_client: Optional[HTTPClient] = None

def get_client() -> HTTPClient:
    global _default_client
    if _default_client is None:
        _default_client = HTTPClient()
    return _default_client


def get_text(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> str:
    return get_client().get_text(url, params=params, headers=headers)


def get_json(url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    return get_client().get_json(url, params=params, headers=headers)
