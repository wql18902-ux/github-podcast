#!/usr/bin/env python3
"""本地云 TTS 控制台。

只绑定 127.0.0.1。API Key 写入 macOS Keychain，不写项目文件，不回显到前端。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from cloud_tts import (
    CloudTTSError,
    PROVIDER_PRESETS,
    list_public_config,
    synthesize,
    update_provider_config,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = PROJECT_ROOT / "web"
OUTPUT_ROOT = PROJECT_ROOT / "output" / "tts-console"
MAX_JSON_BYTES = 2 * 1024 * 1024


def _safe_project_path(raw: str) -> Path:
    if not raw:
        raise CloudTTSError("路径为空")
    path = (PROJECT_ROOT / raw).resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise CloudTTSError("只允许读取项目目录内的文件") from exc
    if not path.is_file():
        raise CloudTTSError(f"文件不存在: {path}")
    return path


class Handler(BaseHTTPRequestHandler):
    server_version = "TTSConsole/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # 不记录请求体，避免误带密钥。
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, status: int, text: str, content_type: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise CloudTTSError("请求体为空")
        if length > MAX_JSON_BYTES:
            raise CloudTTSError("请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CloudTTSError("请求体不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise CloudTTSError("请求体必须是 JSON 对象")
        return data

    def _check_local_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"https://{host}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                html = (WEB_ROOT / "tts-console.html").read_text(encoding="utf-8")
                self._text(HTTPStatus.OK, html, "text/html; charset=utf-8")
                return
            if path == "/api/health":
                self._json(HTTPStatus.OK, {"ok": True})
                return
            if path == "/api/config":
                self._json(
                    HTTPStatus.OK,
                    {
                        "providers": list_public_config(),
                        "presets": PROVIDER_PRESETS,
                    },
                )
                return
            if path.startswith("/audio/"):
                name = urllib.parse.unquote(path.removeprefix("/audio/"))
                if "/" in name or "\\" in name:
                    raise CloudTTSError("非法文件名")
                target = (OUTPUT_ROOT / name).resolve()
                try:
                    target.relative_to(OUTPUT_ROOT.resolve())
                except ValueError as exc:
                    raise CloudTTSError("非法路径") from exc
                if not target.is_file():
                    raise CloudTTSError("音频不存在")
                body = target.read_bytes()
                mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except CloudTTSError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def do_POST(self) -> None:
        if not self._check_local_origin():
            self._json(HTTPStatus.FORBIDDEN, {"error": "origin rejected"})
            return
        parsed = urllib.parse.urlparse(self.path)
        try:
            data = self._read_json()
            if parsed.path == "/api/config":
                provider = str(data.get("provider") or "")
                extra = data.get("extra") or {}
                if not isinstance(extra, dict):
                    raise CloudTTSError("额外参数必须是 JSON 对象")
                secret = data.get("secret")
                if secret is not None and not isinstance(secret, str):
                    raise CloudTTSError("secret 必须是字符串")
                update_provider_config(
                    provider,
                    adapter=str(data.get("adapter") or ""),
                    endpoint=str(data.get("endpoint") or ""),
                    model=str(data.get("model") or ""),
                    voice=str(data.get("voice") or ""),
                    extra=extra,
                    secret=secret or None,
                    clear_secret=bool(data.get("clear_secret")),
                )
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "providers": list_public_config()},
                )
                return
            if parsed.path == "/api/script":
                target = _safe_project_path(str(data.get("path") or ""))
                text = target.read_text(encoding="utf-8")
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "path": str(target.relative_to(PROJECT_ROOT)),
                        "chars": len(text),
                        "text": text,
                    },
                )
                return
            if parsed.path == "/api/synthesize":
                provider = str(data.get("provider") or "")
                text = str(data.get("text") or "")
                max_chars = int(data.get("max_chars") or 0)
                if max_chars > 0:
                    text = text[:max_chars]
                output = synthesize(provider, text, None)
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "file": output.name,
                        "url": f"/audio/{urllib.parse.quote(output.name)}",
                        "chars": len(text),
                    },
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except CloudTTSError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser(description="本地云 TTS 控制台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"TTS 控制台: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

