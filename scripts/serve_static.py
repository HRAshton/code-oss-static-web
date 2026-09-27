#!/usr/bin/env python3
from __future__ import annotations

import argparse
import posixpath
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class StaticHandler(SimpleHTTPRequestHandler):
    server_version = "CodeOSSStaticWebTestServer/1"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        parsed = urlsplit(path)
        request_path = unquote(parsed.path)
        base_path: str = self.server.base_path  # type: ignore[attr-defined]
        root: Path = self.server.static_root  # type: ignore[attr-defined]

        if base_path != "/":
            prefix = base_path.rstrip("/")
            if request_path == prefix:
                request_path = "/"
            elif request_path.startswith(prefix + "/"):
                request_path = request_path[len(prefix):]
            else:
                return str(root / "__not_found__")

        request_path = posixpath.normpath(request_path)
        parts = [part for part in request_path.split("/") if part not in ("", ".", "..")]
        resolved = root.joinpath(*parts)
        try:
            resolved.relative_to(root)
        except ValueError:
            return str(root / "__not_found__")
        return str(resolved)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a static qualification build")
    parser.add_argument("--directory", type=Path, default=Path("dist"))
    parser.add_argument("--base-path", default="/code-oss-web/")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    args = parser.parse_args()

    root = args.directory.resolve()
    if not (root / "index.html").is_file():
        raise SystemExit(f"not a static distribution: {root}")

    base_path = "/" + args.base_path.strip("/") + "/" if args.base_path != "/" else "/"
    server = ThreadingHTTPServer((args.host, args.port), StaticHandler)
    server.static_root = root  # type: ignore[attr-defined]
    server.base_path = base_path  # type: ignore[attr-defined]
    print(f"serving {root} at http://{args.host}:{args.port}{base_path}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
