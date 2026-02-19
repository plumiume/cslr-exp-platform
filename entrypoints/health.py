#!/usr/bin/env python3
# Health check HTTP server
from typing import Any
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, format: str, *args: Any):
        pass


if __name__ == '__main__':
    HTTPServer(('0.0.0.0', 8080), HealthHandler).serve_forever()
