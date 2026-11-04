"""Preview the generated site at its configured base path. Run build.py first."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from build import DIST, settings

BASE = urlsplit(settings()["SITE_URL"]).path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_GET(self):
        if self.path == "/" and BASE != "/":
            self.send_response(302)
            self.send_header("Location", BASE)
            self.end_headers()
            return
        if not self.path.startswith(BASE):
            self.send_error(404)
            return
        self.path = "/" + self.path[len(BASE):]
        super().do_GET()


if __name__ == "__main__":
    print(f"Preview: http://127.0.0.1:8000{BASE}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
