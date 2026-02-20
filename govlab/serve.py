#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Governor Lab — one-screen demo of the evidence gate.

Usage:
    python3 serve.py [--port 8888] [--state-dir /tmp/govlab_state]

Opens a browser to a single-page demo where you can:
  1. Type agent output (the claim)
  2. See the gate decision (PASS / WARN / BLOCKED)
  3. See the receipt (content-addressed proof)
  4. Tweak the text and re-run
  5. See history of all runs + diffs

Shells out to the `governor` CLI. Requires `governor` on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_PORT = 8888


def find_governor() -> str:
    """Find the governor binary."""
    path = shutil.which("governor")
    if not path:
        print("Error: 'governor' not found on PATH.", file=sys.stderr)
        print("Install: pip install -e /path/to/agent_gov", file=sys.stderr)
        sys.exit(1)
    return path


def init_state(state_dir: Path) -> None:
    """Initialize governor state directory if needed."""
    gov_dir = state_dir / ".governor"
    if not gov_dir.exists():
        subprocess.run(
            [find_governor(), "--root", str(state_dir), "init"],
            capture_output=True,
        )


def run_gate_check(state_dir: Path, text: str, strict: bool = True) -> dict:
    """Run governor gate check and return JSON result + receipt."""
    args = [
        find_governor(), "--root", str(state_dir),
        "gate", "check", "--stdin", "--format", "json",
    ]
    if not strict:
        args.append("--permissive")

    result = subprocess.run(
        args,
        input=text,
        capture_output=True,
        text=True,
        timeout=30,
    )

    gate_result = {}
    if result.stdout.strip():
        try:
            gate_result = json.loads(result.stdout)
        except json.JSONDecodeError:
            gate_result = {"error": result.stdout, "stderr": result.stderr}

    # Fetch the latest receipt
    receipt = get_latest_receipt(state_dir)

    return {
        "gate": gate_result,
        "receipt": receipt,
    }


def get_receipts(state_dir: Path, last: int = 20) -> list[dict]:
    """Get recent receipts."""
    result = subprocess.run(
        [find_governor(), "--root", str(state_dir),
         "receipts", "--json", "--last", str(last)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.stdout.strip():
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
    return []


def get_latest_receipt(state_dir: Path) -> dict | None:
    """Get the single most recent receipt."""
    receipts = get_receipts(state_dir, last=1)
    return receipts[0] if receipts else None


class LabHandler(SimpleHTTPRequestHandler):
    """Request handler for the lab server."""

    state_dir: Path  # Set by factory

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        elif path == "/api/receipts":
            qs = parse_qs(parsed.query)
            last = int(qs.get("last", ["20"])[0])
            receipts = get_receipts(self.state_dir, last=last)
            self._json_response(receipts)
        elif path == "/api/health":
            self._json_response({"status": "ok", "state_dir": str(self.state_dir)})
        else:
            # Try static files
            static_path = STATIC_DIR / path.lstrip("/")
            if static_path.exists() and static_path.is_file():
                content_type = "text/html"
                if path.endswith(".css"):
                    content_type = "text/css"
                elif path.endswith(".js"):
                    content_type = "application/javascript"
                self._serve_file(static_path, content_type)
            else:
                self.send_error(404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_response({"error": "invalid JSON"}, status=400)
            return

        if path == "/api/check":
            text = data.get("text", "")
            strict = data.get("strict", True)
            if not text.strip():
                self._json_response({"error": "empty text"}, status=400)
                return
            result = run_gate_check(self.state_dir, text, strict=strict)
            self._json_response(result)
        elif path == "/api/reset":
            # Reset state — re-init governor
            gov_dir = self.state_dir / ".governor"
            if gov_dir.exists():
                shutil.rmtree(gov_dir)
            init_state(self.state_dir)
            self._json_response({"status": "reset"})
        else:
            self._json_response({"error": "not found"}, status=404)

    def _serve_file(self, path: Path, content_type: str) -> None:
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json_response(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        """Quiet logging — only errors."""
        if args and isinstance(args[0], str) and args[0].startswith("4"):
            super().log_message(format, *args)


def make_handler(state_dir: Path) -> type[LabHandler]:
    """Create a handler class with the state_dir bound."""

    class BoundHandler(LabHandler):
        pass

    BoundHandler.state_dir = state_dir
    return BoundHandler


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Governor Lab")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-dir", type=str, default=None,
                        help="Governor state directory (default: temp dir)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # State directory
    if args.state_dir:
        state_dir = Path(args.state_dir)
        state_dir.mkdir(parents=True, exist_ok=True)
    else:
        state_dir = Path(tempfile.mkdtemp(prefix="govlab_"))
        print(f"State dir: {state_dir}")

    # Initialize governor
    find_governor()  # Fail fast if not installed
    init_state(state_dir)

    handler = make_handler(state_dir)
    server = HTTPServer(("127.0.0.1", args.port), handler)

    url = f"http://127.0.0.1:{args.port}"
    print(f"Governor Lab: {url}")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
