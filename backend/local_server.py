#!/usr/bin/env python3
"""Local API Gateway stand-in.

Translates plain HTTP into the API Gateway REST proxy event shape and calls the
exact same Lambda handlers that run in AWS -- no mock layer, no second
implementation. This is what makes it possible to rehearse the full loop
(select -> edit -> submit -> results -> leaderboard) before anything is deployed,
and what the frontend talks to during development.

    python backend/local_server.py --port 8000
"""
import argparse
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BREAKFIX_STORAGE", "local")

from lambdas.challenges import handler as challenges_handler  # noqa: E402
from lambdas.leaderboard import handler as leaderboard_handler  # noqa: E402
from lambdas.sessions import handler as sessions_handler  # noqa: E402
from lambdas.stats import handler as stats_handler  # noqa: E402
from lambdas.broadcaster import handler as broadcaster_handler  # noqa: E402
from lambdas.admin import handler as admin_handler  # noqa: E402
from lambdas.metrics import handler as metrics_handler  # noqa: E402
import local_ws  # noqa: E402
from common import realtime  # noqa: E402
from lambdas.submit import handler as submit_handler  # noqa: E402

# Tables whose writes the deployed stack streams to the broadcaster. Locally we
# call the SAME broadcaster Lambda with a synthetic stream record after a write,
# so the real handler is exercised in development rather than only after deploy.
STREAMED_WRITES = {
    "POST /sessions": "breakfix-sessions",
    "POST /submit": "breakfix-results",
}


def _fire_stream(table: str) -> None:
    """Stand-in for a DynamoDB Streams trigger."""
    try:
        broadcaster_handler.handler(
            {"Records": [{"eventSourceARN": f"arn:aws:dynamodb:local:000000000000:table/{table}/stream/local",
                          "eventName": "INSERT"}]},
            None,
        )
    except Exception:  # noqa: BLE001
        sys.stderr.write("  [stream] broadcast failed\n")


ROUTES = [
    ("GET", r"^/challenges$", challenges_handler.handler, ()),
    ("POST", r"^/sessions$", sessions_handler.handler, ()),
    ("POST", r"^/sessions/([^/]+)/submit$", submit_handler.handler, ("session_id",)),
    ("GET", r"^/leaderboard$", leaderboard_handler.handler, ()),
    ("GET", r"^/stats$", stats_handler.handler, ()),
    ("GET", r"^/system-status$", metrics_handler.handler, ()),
    # --- admin-only (passphrase gated) ---------------------------------------
    ("POST", r"^/admin/authoring$", admin_handler.start_authoring, ()),
    ("GET", r"^/admin/authoring$", admin_handler.get_authoring, ()),
    ("GET", r"^/admin/authoring/([^/]+)$", admin_handler.get_authoring, ("execution_id",)),
    ("GET", r"^/admin/pending$", admin_handler.list_pending, ()),
    ("POST", r"^/admin/challenges/([^/]+)/publish$", admin_handler.publish, ("challenge_id",)),
    ("POST", r"^/admin/challenges/([^/]+)/reject$", admin_handler.reject, ("challenge_id",)),
]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _dispatch(self, method):
        import re

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""

        if method == "OPTIONS":
            return self._send(204, {}, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Admin-Passphrase",
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            })

        for route_method, pattern, fn, names in ROUTES:
            match = re.match(pattern, path)
            if not match:
                continue
            if route_method != method:
                return self._send(405, {"error": "Method not allowed."}, {})
            event = {
                "httpMethod": method,
                "path": path,
                "body": body,
                "queryStringParameters": query,
                "pathParameters": dict(zip(names, match.groups())),
                "headers": dict(self.headers),
            }
            response = fn(event, None)

            # Mirror the deployed write -> stream -> broadcast path.
            if method == "POST" and 200 <= response.get("statusCode", 500) < 300 and not path.startswith("/admin"):
                table = "breakfix-results" if path.endswith("/submit") else "breakfix-sessions"
                _fire_stream(table)

            headers = response.get("headers", {})
            payload = response.get("body") or "{}"
            return self._send_raw(response["statusCode"], payload, headers)

        return self._send(404, {"error": f"No route for {method} {path}"}, {})

    def _send(self, status, payload, headers):
        self._send_raw(status, json.dumps(payload), {"Content-Type": "application/json", **headers})

    def _send_raw(self, status, payload, headers):
        data = payload.encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if status != 204:
            self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_OPTIONS(self):  # noqa: N802
        self._dispatch("OPTIONS")

    def log_message(self, fmt, *a):  # quieter console during a demo
        sys.stderr.write("  %s\n" % (fmt % a))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ws-port", type=int, default=8001)
    args = parser.parse_args()

    # A dev passphrase so the admin screen is usable locally. In AWS this comes
    # from the stack parameter, and with none set every admin route 503s.
    os.environ.setdefault("ADMIN_PASSPHRASE", "breakfix-dev")
    from common import config as _config
    _config.ADMIN_PASSPHRASE = os.environ["ADMIN_PASSPHRASE"]

    # Local stand-in for the API Gateway WebSocket API.
    local_ws.start(args.ws_port, on_hello=realtime.build_snapshot)

    # Local stand-in for an EventBridge rule: published challenges refresh every
    # connected client's catalogue.
    from common import events as _events
    _events.subscribe(lambda envelope: realtime.broadcast(
        {"type": "event", "detail_type": envelope["detail_type"], "detail": envelope["detail"],
         "at": envelope["at"]}))

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BreakFix API (local Lambda shim) on http://127.0.0.1:{args.port}")
    print(f"  storage: {os.environ['BREAKFIX_STORAGE']}")
    print(f"  REST:      /challenges /sessions /leaderboard /stats /system-status")
    print(f"  Admin:     /admin/authoring /admin/pending /admin/challenges/{{id}}/publish")
    print(f"  Passphrase: {os.environ['ADMIN_PASSPHRASE']}")
    print(f"  WebSocket: ws://127.0.0.1:{args.ws_port}  (snapshot on connect, push on every write)")
    server.serve_forever()


if __name__ == "__main__":
    main()
