"""Small client adapted from codezjx/netease-cloud-music-dl (MIT License).

Copyright (c) 2017 codezjx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

LOGGER = logging.getLogger(__name__)

_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725"
    "152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312e"
    "cbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424d813"
    "cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)
_NONCE = "0CoJUm6Qyw8W8jud"
_PUBLIC_EXPONENT = 0x10001
_BASE_URL = "https://music.163.com"


class NeteaseCloudError(RuntimeError):
    """The public music endpoint did not return usable data."""


@dataclass(frozen=True)
class Song:
    id: int
    title: str
    artists: tuple[str, ...]
    fee: int


@dataclass(frozen=True)
class Playlist:
    title: str
    song_ids: tuple[int, ...]


@dataclass(frozen=True)
class Playback:
    url: str | None
    extension: str
    is_preview: bool


def _aes_encrypt(text: str, key: str) -> str:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(text.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key.encode("ascii")), modes.CBC(b"0102030405060708")).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def _encrypted_request(payload: dict[str, Any]) -> dict[str, str]:
    secret = os.urandom(16).hex()[:16]
    encoded = _aes_encrypt(_aes_encrypt(json.dumps(payload), _NONCE), secret)
    reversed_secret = secret.encode("ascii")[::-1]
    encrypted_secret = pow(
        int.from_bytes(reversed_secret, "big"), _PUBLIC_EXPONENT, int(_MODULUS, 16)
    )
    return {"params": encoded, "encSecKey": f"{encrypted_secret:0256x}"}


class NeteaseCloudClient:
    def __init__(self, timeout: tuple[int, int] = (15, 30)) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
                ),
                "Referer": _BASE_URL,
                "Cookie": f"appver=2.0.2; _ntes_nuid={uuid.uuid4().hex}; NMTID={uuid.uuid4().hex}",
            }
        )

    def _get(self, path: str) -> dict[str, Any]:
        response = self.session.get(f"{_BASE_URL}{path}", timeout=self.timeout)
        response.raise_for_status()
        return self._json(response)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{_BASE_URL}{path}",
            data=_encrypted_request(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return self._json(response)

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            result = response.json()
        except ValueError as exc:
            raise NeteaseCloudError("网易云音乐返回了非 JSON 响应。") from exc
        if not isinstance(result, dict) or result.get("code") != 200:
            raise NeteaseCloudError(f"网易云音乐接口返回异常：{result.get('code') if isinstance(result, dict) else '格式错误'}。")
        return result

    def song(self, song_id: int) -> Song:
        result = self._get(f"/api/song/detail/?ids=[{song_id}]")
        songs = result.get("songs") or []
        if not songs:
            raise NeteaseCloudError(f"找不到歌曲 {song_id}。")
        entry = songs[0]
        artists = tuple(
            str(artist.get("name", "")).strip()
            for artist in entry.get("artists", [])
            if artist.get("name")
        )
        song = Song(
            id=int(entry["id"]),
            title=str(entry.get("name") or "").strip(),
            artists=artists,
            fee=int(entry.get("fee") or 0),
        )
        LOGGER.info("Netease song resolved id=%s title=%s fee=%s", song.id, song.title, song.fee)
        return song

    def playlist(self, playlist_id: int) -> Playlist:
        result = self._get(f"/api/v6/playlist/detail?id={playlist_id}")
        entry = result.get("playlist")
        if not isinstance(entry, dict):
            raise NeteaseCloudError("找不到这个公开歌单。")
        playlist = Playlist(
            title=str(entry.get("name") or "").strip(),
            song_ids=tuple(int(track["id"]) for track in entry.get("trackIds", [])),
        )
        LOGGER.info(
            "Netease playlist resolved id=%s title=%s tracks=%d",
            playlist_id,
            playlist.title,
            len(playlist.song_ids),
        )
        return playlist

    def playback(self, song_id: int) -> Playback:
        result = self._post(
            "/weapi/song/enhance/player/url?csrf_token=",
            {"ids": [song_id], "br": 320000, "csrf_token": ""},
        )
        items = result.get("data") or []
        if not items:
            raise NeteaseCloudError(f"歌曲 {song_id} 没有播放信息。")
        item = items[0]
        extension = str(item.get("type") or "mp3").lower()
        if extension not in {"mp3", "flac", "m4a", "aac"}:
            raise NeteaseCloudError(f"歌曲 {song_id} 返回了不支持的音频格式：{extension}。")
        playback = Playback(
            url=item.get("url") or None,
            extension=extension,
            is_preview=item.get("freeTrialInfo") is not None,
        )
        LOGGER.info(
            "Netease playback resolved id=%s available=%s preview=%s format=%s",
            song_id,
            bool(playback.url),
            playback.is_preview,
            playback.extension,
        )
        return playback
