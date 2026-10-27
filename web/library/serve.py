#!/usr/bin/env python3
"""页声 · 静态站点服务（支持 Range，音频进度条才能拖动）。

部署环境从 $PORT 取端口、绑 0.0.0.0；本地直接跑默认 3000：

    python3 serve.py
"""
from __future__ import annotations

import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class _Bounded:
    """只把请求的那一段字节交给 http.server 的 copyfile。"""

    def __init__(self, fh, remaining: int) -> None:
        self.fh = fh
        self.remaining = remaining

    def read(self, n: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        if n is None or n < 0:
            n = self.remaining
        data = self.fh.read(min(n, self.remaining))
        self.remaining -= len(data)
        return data

    def close(self) -> None:
        self.fh.close()


class RangeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        rng = self.headers.get("Range")
        path = self.translate_path(self.path)
        if not rng or os.path.isdir(path) or not os.path.isfile(path):
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
        if not m:
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1) or 0)
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        fh = open(path, "rb")
        fh.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        return _Bounded(fh, end - start + 1)

    def log_message(self, fmt, *args):
        pass


def main() -> int:
    port = int(os.environ.get("PORT", "3000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), RangeHandler)
    print(f"serving {ROOT} on 0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
