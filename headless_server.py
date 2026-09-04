#!/usr/bin/env python3
"""A small, read-only HTTP server for publishing any selected folder."""

import argparse
import html
import io
import ipaddress
import os
import sys
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlsplit, urlunsplit


DEFAULT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
PREFERRED_PYTHON = "/opt/homebrew/bin/python3"
SERVE_MODES = {"index", "list"}


SimpleHTTPRequestHandler.extensions_map.update({
    ".wasm": "application/wasm",
    ".step": "model/step",
    ".stp": "model/step",
    ".stl": "model/stl",
    ".js": "application/javascript",
    ".json": "application/json",
})


def clean_log_value(value):
    """Escape control characters so a request cannot manipulate the terminal."""
    return "".join(
        char if ord(char) >= 32 and ord(char) != 127 else f"\\x{ord(char):02x}"
        for char in str(value)
    )


def use_supported_python_if_available():
    """Replace the unsupported macOS Python 3.9 runtime when Homebrew is present."""
    if sys.version_info < (3, 12) and os.path.isfile(PREFERRED_PYTHON):
        os.execv(PREFERRED_PYTHON, [PREFERRED_PYTHON, *sys.argv])


def format_size(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024


class FolderRequestHandler(SimpleHTTPRequestHandler):
    """Serve one folder without uploads, proxying, or path traversal."""

    server_version = "FolderWeb"
    sys_version = ""

    def version_string(self):
        return self.server_version

    @property
    def serve_mode(self):
        return getattr(self.server, "serve_mode", "index")

    def _valid_request_target(self):
        target = self.path
        if not target.startswith("/") or target.startswith("//"):
            return False
        parsed = urlsplit(target)
        return not parsed.scheme and not parsed.netloc and "\x00" not in target

    def _prepare_request(self):
        if not self._valid_request_target():
            self.send_error(400, "Invalid request target")
            return False
        query = urlsplit(self.path).query.split("&")
        self._force_download = self.serve_mode == "list" and "download=1" in query
        return True

    def translate_path(self, path):
        translated = super().translate_path(path)
        root = os.path.realpath(self.directory)
        resolved = os.path.realpath(translated)
        try:
            inside_root = os.path.commonpath((root, resolved)) == root
        except ValueError:
            inside_root = False
        if not inside_root:
            return os.path.join(root, ".folder-web-blocked-path")
        return translated

    def send_head(self):
        if self.serve_mode == "list":
            path = self.translate_path(self.path)
            if os.path.isdir(path):
                parsed = urlsplit(self.path)
                if not parsed.path.endswith("/"):
                    new_parts = ("", "", parsed.path + "/", parsed.query, parsed.fragment)
                    self.send_response(301)
                    self.send_header("Location", urlunsplit(new_parts))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                return self.list_directory(path)
        return super().send_head()

    def list_directory(self, path):
        if self.serve_mode != "list":
            self.send_error(404, "No index.html in this directory")
            return None

        try:
            entries = sorted(
                os.scandir(path),
                key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.lower()),
            )
        except OSError:
            self.send_error(404, "Directory cannot be listed")
            return None

        request_path = unquote(urlsplit(self.path).path, errors="surrogatepass")
        display_path = html.escape(request_path)
        rows = []
        if request_path != "/":
            rows.append('<li class="folder"><a href="../">📁 上一级目录</a></li>')

        for entry in entries:
            name = entry.name
            display_name = html.escape(name, quote=False)
            link_name = quote(name, errors="surrogatepass")
            try:
                if entry.is_dir(follow_symlinks=False):
                    rows.append(
                        f'<li class="folder"><a href="{link_name}/">📁 {display_name}/</a>'
                        '<span>文件夹</span></li>'
                    )
                    continue
                stat = entry.stat(follow_symlinks=False)
                modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                size = format_size(stat.st_size)
            except OSError:
                modified = "—"
                size = "—"
            rows.append(
                f'<li><a href="{link_name}?download=1">📄 {display_name}</a>'
                f'<span>{html.escape(size)} · {html.escape(modified)}</span></li>'
            )

        page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>文件下载 · {display_path}</title>
  <style>
    :root {{ color-scheme: light dark; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    body {{ max-width: 900px; margin: 0 auto; padding: 24px 18px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(22px,5vw,34px); }}
    .hint {{ margin: 0 0 20px; color: #6b7280; }}
    ul {{ list-style: none; margin: 0; padding: 0; border: 1px solid #d1d5db; border-radius: 12px; overflow: hidden; }}
    li {{ display: flex; justify-content: space-between; gap: 16px; padding: 12px 14px; border-bottom: 1px solid #d1d5db; }}
    li:last-child {{ border-bottom: 0; }}
    li:hover {{ background: rgba(127,127,127,.10); }}
    a {{ color: #2563eb; text-decoration: none; overflow-wrap: anywhere; }}
    span {{ color: #6b7280; white-space: nowrap; font-size: 14px; }}
    @media (max-width: 560px) {{ li {{ align-items: flex-start; flex-direction: column; gap: 4px; }} }}
  </style>
</head>
<body>
  <h1>文件下载</h1>
  <p class="hint">当前目录：{display_path}</p>
  <ul>{''.join(rows)}</ul>
</body>
</html>
""".encode("utf-8", "surrogateescape")
        stream = io.BytesIO(page)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        return stream

    def end_headers(self):
        if getattr(self, "_force_download", False):
            filename = os.path.basename(unquote(urlsplit(self.path).path)) or "download"
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(filename)}")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        super().end_headers()

    def do_GET(self):
        if self._prepare_request():
            super().do_GET()

    def do_HEAD(self):
        if self._prepare_request():
            super().do_HEAD()

    def do_POST(self):
        self.send_error(405, "Method not allowed")

    do_PUT = do_POST
    do_DELETE = do_POST
    do_OPTIONS = do_POST
    do_CONNECT = do_POST

    def log_message(self, format, *args):
        message = clean_log_value(format % args)
        sys.stdout.write(
            f"[{self.log_date_time_string()}] "
            f"{clean_log_value(self.address_string())} - {message}\n"
        )
        sys.stdout.flush()


# Keep the old import name working for existing launchers.
SecureStaticRequestHandler = FolderRequestHandler


class SecureThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(15)
        return request, client_address


def parse_arguments():
    parser = argparse.ArgumentParser(description="将一个文件夹发布为只读 HTTP 网站")
    parser.add_argument("legacy_directory", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("legacy_port", nargs="?", type=int, help=argparse.SUPPRESS)
    parser.add_argument("legacy_host", nargs="?", help=argparse.SUPPRESS)
    parser.add_argument("legacy_mode", nargs="?", choices=sorted(SERVE_MODES), help=argparse.SUPPRESS)
    parser.add_argument("-d", "--directory", help="要发布的文件夹")
    parser.add_argument("-p", "--port", type=int, help="监听端口，默认 9090")
    parser.add_argument("-b", "--bind", dest="host", help="监听 IPv4 地址，默认 0.0.0.0")
    parser.add_argument(
        "-m",
        "--mode",
        choices=sorted(SERVE_MODES),
        help="index：使用 index.html；list：显示文件下载列表",
    )
    args = parser.parse_args()
    args.directory = args.directory or args.legacy_directory or DEFAULT_DIRECTORY
    args.port = args.port or args.legacy_port or 9090
    args.host = args.host or args.legacy_host or "0.0.0.0"
    args.mode = args.mode or args.legacy_mode or "index"
    return args


def main():
    args = parse_arguments()
    serve_dir = os.path.abspath(os.path.expanduser(args.directory))

    if not os.path.isdir(serve_dir):
        sys.stderr.write(f"错误：目录不存在：{serve_dir}\n")
        return 1
    try:
        address = ipaddress.ip_address(args.host)
        if address.version != 4:
            raise ValueError
    except ValueError:
        sys.stderr.write("错误：监听 IP 必须是有效的 IPv4 地址，例如 127.0.0.1 或 0.0.0.0\n")
        return 1
    if not 1 <= args.port <= 65535:
        sys.stderr.write("错误：端口必须在 1 到 65535 之间\n")
        return 1

    handler = partial(FolderRequestHandler, directory=serve_dir)
    try:
        httpd = SecureThreadingHTTPServer((args.host, args.port), handler)
        httpd.serve_mode = args.mode
        mode_text = "index.html 首页" if args.mode == "index" else "文件下载列表"
        scope = "所有网络接口" if args.host == "0.0.0.0" else args.host
        sys.stdout.write(f"🚀 文件夹网站服务已启动：http://{args.host}:{args.port}/\n")
        sys.stdout.write(f"📂 服务目录：{serve_dir}\n")
        sys.stdout.write(f"🧭 展示模式：{mode_text}；监听范围：{scope}\n")
        sys.stdout.flush()
        httpd.serve_forever()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        sys.stderr.write(f"错误：{exc}\n")
        return 1


if __name__ == "__main__":
    use_supported_python_if_available()
    raise SystemExit(main())
