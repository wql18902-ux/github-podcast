#!/usr/bin/env python3
"""私台 · 本地预览服务（支持 Range，<audio> 才能拖动进度条）。

python -m http.server 不支持 Range：它对 Range 请求照样回 200，
浏览器拿不到 206 就不认为这份媒体可 seek，进度条拖不动。
手机上试听、逐段跳转都会失效，所以本地预览用这个。

    python3 scripts/preview_radio.py [端口]

默认服务 `web/private-radio`；要预览别的目录（例如 `web/library`）设环境变量：

    PREVIEW_ROOT=web/library python3 scripts/preview_radio.py 8793
"""

from __future__ import annotations

import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(
    os.environ.get("PREVIEW_ROOT")
    or Path(__file__).resolve().parent.parent / "web" / "private-radio"
).expanduser().resolve()


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

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._range_left = end - start + 1
        return _Bounded(f, self._range_left)

    def log_message(self, fmt, *args):
        pass


class _Bounded:
    """只让 copyfile 读到指定长度，避免把整个文件灌进响应。"""

    def __init__(self, fh, remaining):
        self.fh = fh
        self.remaining = remaining

    def read(self, n=-1):
        if self.remaining <= 0:
            return b""
        if n is None or n < 0:
            n = self.remaining
        data = self.fh.read(min(n, self.remaining))
        self.remaining -= len(data)
        return data

    def close(self):
        self.fh.close()


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8791
    srv = ThreadingHTTPServer(("127.0.0.1", port), RangeHandler)
    print(f"本地预览（支持 Range）→ http://127.0.0.1:{port}/  根目录 {ROOT}")
    print("Ctrl-C 结束")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
