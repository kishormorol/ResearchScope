"""Serve the static site locally with extensionless HTML routes.

For example, /conferences is served from site/conferences.html, matching the
production GitHub Pages URL structure.
"""

from __future__ import annotations

import argparse
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

PRODUCTION_API = "https://researchscope-production.up.railway.app"
PRODUCTION_PAPERS_PROXY = "/api/production/papers"
PRODUCTION_SEARCH_PROXY = "/api/production/search"


class ExtensionlessHtmlHandler(SimpleHTTPRequestHandler):
    """Fall back to an .html file for extensionless paths."""

    def do_GET(self) -> None:
        request = urlsplit(self.path)
        if request.path == PRODUCTION_PAPERS_PROXY:
            self._proxy_production_get("/papers", request.query, "production-papers")
            return
        if request.path == PRODUCTION_SEARCH_PROXY:
            self._proxy_production_get("/search", request.query, "production-search")
            return
        super().do_GET()

    def _proxy_production_get(
        self, upstream_path: str, query: str, upstream_label: str
    ) -> None:
        """Proxy an allowlisted public catalog endpoint for local UI use."""
        upstream_url = f"{PRODUCTION_API}{upstream_path}"
        if query:
            upstream_url = f"{upstream_url}?{query}"

        try:
            with urlopen(
                Request(
                    upstream_url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "ResearchScope-local-dev/1.0",
                    },
                ),
                timeout=20,
            ) as upstream:
                body = upstream.read()
                status = upstream.status
                content_type = upstream.headers.get(
                    "Content-Type", "application/json"
                )
            self.send_response(status)
            self.send_header(
                "Content-Type",
                content_type,
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-ResearchScope-Upstream", upstream_label)
            self.end_headers()
            self.wfile.write(body)
        except HTTPError as exc:
            body = exc.read()
            self.send_response(exc.code)
            self.send_header(
                "Content-Type", exc.headers.get("Content-Type", "application/json")
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (URLError, TimeoutError) as exc:
            body = b'{"detail":"Production catalog API is unavailable locally"}'
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.log_error("Production catalog proxy failed: %s", exc)

    def end_headers(self) -> None:
        # Local development should always reflect the current frontend files.
        # This also prevents an older API-base selection script from continuing
        # to point localhost pages at the production Railway service.
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        file_path = super().translate_path(path)
        request_path = urlsplit(path).path

        if not Path(request_path).suffix and not os.path.exists(file_path):
            html_path = f"{file_path}.html"
            if os.path.isfile(html_path):
                return html_path

        return file_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the ResearchScope site locally."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site",
    )
    args = parser.parse_args()

    handler = partial(ExtensionlessHtmlHandler, directory=str(args.directory.resolve()))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {args.directory} at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
