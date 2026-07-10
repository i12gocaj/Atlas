"""Tests del servidor estatico local."""

from __future__ import annotations

from atlas import server


def test_serve_binds_only_to_ipv4_loopback(monkeypatch):
    observed = {}

    class FakeServer:
        def __init__(self, address, handler):
            observed["address"] = address
            observed["handler"] = handler

        def serve_forever(self):
            raise KeyboardInterrupt

        def shutdown(self):
            observed["shutdown"] = True

    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeServer)

    server.serve("dashboard", 9123)

    assert observed["address"] == ("127.0.0.1", 9123)
    assert observed["shutdown"] is True
