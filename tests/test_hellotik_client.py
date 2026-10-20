from __future__ import annotations

from typing import Any

from hellotik_client import HelloTikClient


class _Response:
    def __init__(self, status_code: int, data: dict[str, Any]) -> None:
        self.status_code = status_code
        self.ok = status_code < 400
        self._data = data

    def json(self) -> dict[str, Any]:
        return self._data


class _Session:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def post(self, url: str, json: dict[str, Any], timeout: object) -> _Response:
        self.calls.append((url, json))
        if url.endswith("/api/parse-entitlement-status"):
            return _Response(
                200,
                {"quoteToken": "quote", "data": {"defaultTier": "standard"}},
            )
        if "/api/gate-" in url:
            return _Response(200, {"tk_e5eea8": "ticket", "sd_e5eea8": "seed"})
        return _Response(200, {"status": 0, "data": {"type": "video"}})


def test_parse_adds_current_page_entitlement_before_encrypting() -> None:
    client = HelloTikClient()
    session = _Session()
    client.session = session  # type: ignore[assignment]
    encrypted_payload: dict[str, Any] = {}

    def capture_payload(payload: dict[str, Any], ticket: tuple[str, str]) -> dict[str, Any]:
        encrypted_payload.update(payload)
        assert ticket == ("ticket", "seed")
        return {"request": "encrypted"}

    client._encrypt_request = capture_payload  # type: ignore[method-assign]

    assert client.parse("https://xhslink.cn/o/example") == {"type": "video"}

    entitlement_url, entitlement_body = session.calls[0]
    assert entitlement_url.endswith("/api/parse-entitlement-status")
    assert entitlement_body["page_path"] == "/zh/rednote"
    assert entitlement_body["request_url"] == "https://xhslink.cn/o/example"
    assert encrypted_payload["quoteToken"] == "quote"
    assert encrypted_payload["qualityTier"] == "standard"
    assert encrypted_payload["browserQuota"]["dailyLimit"] == 10


def test_unavailable_upstream_content_has_a_clear_error_message() -> None:
    assert HelloTikClient._error_message({"status": 403}, None) == (
        "解析服务无法读取该小红书内容；内容可能已删除、设为私密或暂时不可见。"
    )
