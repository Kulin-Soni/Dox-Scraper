import threading
import http.server
from urllib.parse import urlparse, parse_qs

# ---------------------------------------------------------------------------
# Local proxy server
# ---------------------------------------------------------------------------


class IframeProxyHandler(http.server.BaseHTTPRequestHandler):
    """
    Serves a minimal HTML page that embeds a target URL in an <iframe>.
    The target URL is passed as the `url` query parameter.
    This lets Camoufox load player pages that block direct navigation.
    """

    def _build_html(self, embed_url: str) -> bytes:
        return f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Player</title>
            </head>
            <body style="width: 100dvw; height: 100dvh;">
                <iframe src="{embed_url}" width="100%" height="100%"
                        frameborder="0" scrolling="no" allowfullscreen muted></iframe>
            </body>
            </html>
        """.encode()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        embed_url = params.get("url", [""])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(self._build_html(embed_url))

    def log_message(self, *_):
        pass  # Silence default access logs


class ProxyServer:
    """Wraps HTTPServer in a daemon thread so it doesn't block the event loop."""

    _server: http.server.HTTPServer

    def __init__(self) -> None:
        pass

    def launch(self):
        self._server = http.server.HTTPServer(("localhost", 8280), IframeProxyHandler)
        # Suppress BrokenPipeError noise when clients disconnect early
        self._server.handle_error = lambda *_: None  # type: ignore
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self):
        self._server.shutdown()