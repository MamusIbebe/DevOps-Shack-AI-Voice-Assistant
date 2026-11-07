"""Tests for the read-only diagnostic tools."""

import http.server
import threading

import pytest

from app.tools import dispatch_tool


@pytest.fixture
def local_server():
    """A tiny HTTP server on localhost that answers 200 on / and redirects /go to the metadata IP."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/go":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            else:
                self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()


def test_system_metrics_return_ok():
    for name in ("check_cpu_usage", "check_memory_usage", "check_disk_usage"):
        event, result = dispatch_tool(name, {})
        assert result["result"] == "ok", name
        assert event["name"] == name


def test_http_check_works_on_localhost(local_server):
    _, result = dispatch_tool("check_http_endpoint", {"url": f"http://127.0.0.1:{local_server}/"})
    assert result["status_code"] == 200


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",
    "http://[fe80::1]/",
    "file:///etc/passwd",
])
def test_http_check_refuses_metadata_and_other_schemes(url):
    _, result = dispatch_tool("check_http_endpoint", {"url": url})
    assert result["result"] == "failed"
    assert "status_code" not in result


def test_http_check_does_not_follow_redirects(local_server):
    _, result = dispatch_tool("check_http_endpoint", {"url": f"http://127.0.0.1:{local_server}/go"})
    assert result["status_code"] == 302


def test_port_check_refuses_metadata_address():
    _, result = dispatch_tool("check_local_port", {"host": "169.254.169.254", "port": 80})
    assert result["reachable"] is False
    assert "not allowed" in result["summary"]


def test_port_check_rejects_invalid_port():
    _, result = dispatch_tool("check_local_port", {"port": 70000})
    assert result["result"] == "failed"


def test_unknown_tool_is_refused():
    _, result = dispatch_tool("delete_everything", {})
    assert result["result"] == "failed"
