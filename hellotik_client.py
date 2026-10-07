"""Unofficial client for the public HelloTik RedNote web flow.

The site currently uses a short-lived ticket plus AES-GCM request envelope.  Keep
the profile values together: HelloTik rotates them from time to time.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

LOGGER = logging.getLogger(__name__)


class HelloTikError(RuntimeError):
    """A request was accepted by HelloTik but could not be parsed."""


@dataclass(frozen=True)
class _Profile:
    auth_route: str = "gate-e5eea8"
    ticket_key: str = "tk_e5eea8"
    seed_key: str = "sd_e5eea8"
    request_ticket_key: str = "tk_e5eea8"
    request_payload_key: str = "pl_e5eea8"
    request_iv_key: str = "iv_e5eea8"
    request_version_key: str = "vr_e5eea8"


class HelloTikClient:
    BASE_URL = "https://www.hellotik.app"
    PROFILE = _Profile()
    # This is the response-decryption value embedded in HelloTik's current
    # browser bundle; it is distinct from the response field named ``key``.
    OUTPUT_DECRYPTION_KEY = "93838338562359368888868323563256"

    def __init__(self, timeout: tuple[int, int] = (15, 90)) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
                ),
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/zh/rednote",
            }
        )

    def parse(self, source_url: str) -> dict[str, Any]:
        source_url = source_url.strip()
        if not source_url.startswith(("https://", "http://")):
            raise HelloTikError("链接必须以 http:// 或 https:// 开头。")

        payload = {
            "requestURL": source_url,
            "isMobile": "false",
            "isoCode": "Other",
            "adType": "adsense",
            "uwx_id": uuid.uuid4().hex,
            "successCount": "0",
            "totalSuccessCount": "0",
            "firstSuccessDate": None,
            "geoipIp": "",
        }
        LOGGER.info("HelloTik parse requested")
        ticket = self._get_ticket(source_url)
        body = self._encrypt_request(payload, ticket)
        response = self.session.post(
            f"{self.BASE_URL}/api/parse", json=body, timeout=self.timeout
        )
        result = self._json(response)
        if not response.ok:
            raise HelloTikError(self._error_message(result, response.status_code))
        if result.get("status") != 0:
            raise HelloTikError(self._error_message(result, None))

        data = result.get("data")
        if result.get("encrypt"):
            data = self._decrypt_result(data, result.get("key", ""))
        if not isinstance(data, dict):
            raise HelloTikError("解析结果格式异常。")
        LOGGER.info(
            "HelloTik parse completed media_type=%s videos=%d images=%d title_present=%s",
            data.get("type"),
            len(data.get("videos") or []),
            len(data.get("pics") or []),
            bool(str(data.get("title") or "").strip()),
        )
        return data

    def _get_ticket(self, source_url: str) -> tuple[str, str]:
        LOGGER.debug("Requesting HelloTik parse ticket")
        response = self.session.post(
            f"{self.BASE_URL}/api/{self.PROFILE.auth_route}",
            json={"requestURL": source_url, "isBatch": False, "mode": "single"},
            timeout=self.timeout,
        )
        result = self._json(response)
        if not response.ok:
            raise HelloTikError(self._error_message(result, response.status_code))
        try:
            LOGGER.debug("HelloTik parse ticket received")
            return result[self.PROFILE.ticket_key], result[self.PROFILE.seed_key]
        except KeyError as exc:
            raise HelloTikError("未取得解析票据；网页协议可能已经更新。") from exc

    def _encrypt_request(
        self, payload: dict[str, Any], ticket: tuple[str, str]
    ) -> dict[str, Any]:
        parse_ticket, seed = ticket
        iv = os.urandom(12)
        key = hashlib.sha256(f"{parse_ticket}:{seed}".encode()).digest()
        encrypted = AESGCM(key).encrypt(
            iv, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), None
        )
        b64 = lambda value: base64.b64encode(value).decode("ascii")
        return {
            self.PROFILE.request_ticket_key: parse_ticket,
            self.PROFILE.request_payload_key: b64(encrypted),
            self.PROFILE.request_iv_key: b64(iv),
            self.PROFILE.request_version_key: 1,
        }

    @staticmethod
    def _decode_base64(value: str) -> bytes:
        return base64.b64decode(value + "=" * (-len(value) % 4))

    def _decrypt_result(self, encrypted: str, encrypted_iv: str) -> dict[str, Any]:
        if not isinstance(encrypted, str) or not isinstance(encrypted_iv, str):
            raise HelloTikError("加密结果缺少必要字段。")

        custom = "ZYXABCDEFGHIJKLMNOPQRSTUVWzyxabcdefghijklmnopqrstuvw9876543210-_"
        normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        translate = str.maketrans(custom, normal)

        def transform(value: str) -> str:
            raw = self._decode_base64(value).decode("latin-1")
            raw = "".join(chr(ord(char) ^ 90) for char in raw)
            raw = "".join(raw[i : i + 8][::-1] for i in range(0, len(raw), 8))
            return raw.translate(translate)

        ciphertext = self._decode_base64(transform(encrypted))
        iv = self._decode_base64(transform(encrypted_iv))
        cipher = Cipher(
            algorithms.AES(self.OUTPUT_DECRYPTION_KEY.encode()), modes.CBC(iv)
        ).decryptor()
        padded = cipher.update(ciphertext) + cipher.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        plaintext = unpadder.update(padded) + unpadder.finalize()
        return json.loads(plaintext.decode("utf-8"))

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            result = response.json()
        except ValueError as exc:
            raise HelloTikError("服务返回了非 JSON 响应。") from exc
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _error_message(result: dict[str, Any], status_code: int | None) -> str:
        message = result.get("error") or result.get("message") or result.get("msg")
        if message:
            return str(message)
        if status_code:
            return f"解析服务返回 HTTP {status_code}。"
        return "链接无法解析或服务暂时拒绝请求。"
