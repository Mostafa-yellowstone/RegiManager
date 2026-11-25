"""Local fixture demo. Binds to loopback and never runs a portal login."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from quoting.carriers.registry import REGISTRY
from quoting.demo.scenarios import SCENARIO_LABELS, scenario_form
from quoting.engine.secrets import status_for
from quoting.intake import ny_today
from quoting.present import render_desk
from quoting.service import run_from_form

BANNER = (
    "Sample applicant loaded for the fixture demo. Premiums are not carrier rates. "
    "This page does not log in to a portal, and it does not accept a password."
)
MAX_BODY = 80_000


def desk_html(*, form, result, scenario: str | None) -> str:
    return render_desk(
        form=form,
        result=result,
        secrets=status_for(REGISTRY.for_line("personal_auto", "NY")),
        banner=BANNER,
        scenario=scenario,
    )


def check_scenarios() -> int:
    """Print each sample path. Returns 0 when every stop has no premium."""

    today = ny_today()
    failed = False
    for key, label in SCENARIO_LABELS.items():
        form = scenario_form(key, today)
        result = run_from_form(form, mode="demo", today=today)
        print(f"{label}")
        if result.status != "completed":
            failed = True
            for issue in result.issues:
                print(f"  intake: {issue.message}")
            continue
        for item in result.results:
            if item.status == "quoted" and item.offer is not None:
                print(f"  {item.carrier_name}: ${item.offer.term_premium} fixture {item.offer.quote_number}")
                if not item.offer.quote_number.startswith("DEMO-") or not item.offer.illustrative:
                    failed = True
            elif item.blocker is not None:
                missing = "; ".join(item.blocker.missing)
                print(f"  {item.carrier_name}: stopped ({item.blocker.code}) — {missing}")
                if item.offer is not None:
                    failed = True
            else:
                failed = True
                print(f"  {item.carrier_name}: unfinished")
    return 1 if failed else 0


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "RegiManagerQuoting/1.0"

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/quoting"):
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        query = parse_qs(parsed.query)
        scenario = (query.get("scenario") or ["clean"])[0]
        form = scenario_form(scenario, ny_today())
        if form is None:
            scenario = "clean"
            form = scenario_form(scenario, ny_today())
        body = desk_html(form=form, result=None, scenario=scenario)
        self._send(200, body, "text/html; charset=utf-8")

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/quoting"):
            self._send(404, "Not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or "0")
        if length > MAX_BODY:
            self._send(413, "Form is too large", "text/plain; charset=utf-8")
            return
        raw = self.rfile.read(length).decode("utf-8", "replace")
        data = parse_qs(raw, keep_blank_values=True)
        today = ny_today()
        result = run_from_form(data, today=today)
        query = parse_qs(parsed.query)
        scenario = (query.get("scenario") or [None])[0]
        body = desk_html(form=data, result=result, scenario=scenario)
        self._send(200, body, "text/html; charset=utf-8")

    def log_message(self, fmt, *args):
        # Skip the default stderr access log. It is not useful in the demo.
        return

    def _send(self, status: int, body: str, content_type: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)
    print(f"NY auto quoting demo at http://127.0.0.1:{port}")
    print("Fixture quotes only. Portal login is not run. Ctrl+C stops the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the New York personal auto quoting demo.")
    parser.add_argument("--check", action="store_true", help="Print the sample quote paths and exit.")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.check:
        return check_scenarios()
    serve(args.port)
    return 0
