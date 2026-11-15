"""URL verification pins validated IPs; all transports here are local mocks."""

import importlib.util
import io
from pathlib import Path
import socket
import ssl
import urllib.request

import pytest

HELPER = (
    Path(__file__).resolve().parents[1]
    / "plugins/muse-github/skills/muse-github-setup/templates/.github/scripts/muse_audit_triage.py"
)
spec = importlib.util.spec_from_file_location("muse_triage_url", HELPER)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)
PUBLIC = "93.184.216.34"


def address(ip=PUBLIC, port=80):
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))


class FakeSocket:
    def __init__(self, body, connections, requests):
        self.body, self.connections, self.requests = body, connections, requests
        self.closed = False
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def setsockopt(self, *args):
        pass

    def connect(self, sockaddr):
        self.connections.append(sockaddr)

    def sendall(self, data):
        self.requests.append(data)

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.body)

    def close(self):
        self.closed = True


@pytest.fixture
def transport(monkeypatch):
    connections, requests, sockets, bodies = [], [], [], []

    def create(*args, **kwargs):
        body = (
            bodies.pop(0) if bodies else b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        )
        result = FakeSocket(body, connections, requests)
        sockets.append(result)
        return result

    monkeypatch.setattr(triage.socket, "socket", create)
    return connections, requests, sockets, bodies


def test_previous_validate_then_urllib_pattern_can_rebind_in_local_mock(
    monkeypatch, transport
):
    """Reproduce the reported gap without contacting either returned address."""
    calls = []

    def dns(host, port, *args, **kwargs):
        calls.append((host, port))
        return [address(PUBLIC if len(calls) == 1 else "127.0.0.1", port)]

    monkeypatch.setattr(triage.socket, "getaddrinfo", dns)
    triage.assert_public_url("http://docs.example.test/")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://docs.example.test/", timeout=1) as response:
        assert response.status == 200
    assert len(calls) == 2 and transport[0] == [("127.0.0.1", 80)]


def test_verification_never_resolves_again_and_preserves_http_host(
    monkeypatch, transport
):
    calls = []

    def dns(host, port, *args, **kwargs):
        calls.append((host, port))
        return [address(PUBLIC if len(calls) == 1 else "127.0.0.1", port)]

    monkeypatch.setattr(triage.socket, "getaddrinfo", dns)
    assert triage.check_url("http://docs.example.test:8080/page?query=1#fragment") == (
        "pass",
        "HTTP 200",
    )
    assert calls == [("docs.example.test", 8080)]
    assert transport[0] == [(PUBLIC, 8080)]
    request = b"".join(transport[1])
    assert b"HEAD /page?query=1 HTTP/1.1" in request
    assert b"Host: docs.example.test:8080" in request
    assert b"fragment" not in request and b"Authorization:" not in request


def test_https_retains_default_certificate_checks_and_original_sni(
    monkeypatch, transport
):
    monkeypatch.setattr(
        triage.socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [address(PUBLIC, port)],
    )
    seen = []

    def wrap(context, connection, *, server_hostname):
        seen.append((context.verify_mode, context.check_hostname, server_hostname))
        return connection

    monkeypatch.setattr(triage.ssl.SSLContext, "wrap_socket", wrap)
    assert triage.check_url("https://docs.example.test/path") == ("pass", "HTTP 200")
    assert seen == [(ssl.CERT_REQUIRED, True, "docs.example.test")]
    assert transport[0] == [(PUBLIC, 443)]
    assert b"Host: docs.example.test\r\n" in b"".join(transport[1])


def test_certificate_failure_is_not_accepted(monkeypatch, transport):
    monkeypatch.setattr(
        triage.socket,
        "getaddrinfo",
        lambda host, port, **kwargs: [address(PUBLIC, port)],
    )

    def reject(*args, **kwargs):
        raise ssl.SSLCertVerificationError("certificate mismatch")

    monkeypatch.setattr(triage.ssl.SSLContext, "wrap_socket", reject)
    verdict, detail = triage.check_url("https://docs.example.test/")
    assert verdict == "fail" and "certificate mismatch" in detail
    assert transport[2][0].closed


def test_tls_receives_only_the_timeout_remaining_after_tcp_connect(monkeypatch):
    clock = [0.0]
    connection = FakeSocket(b"", [], [])
    monkeypatch.setattr(triage.time, "monotonic", lambda: clock[0])

    def connect(*args):
        clock[0] = 9.0
        return connection

    monkeypatch.setattr(triage, "_connect_public", connect)
    timeouts = []

    def wrap(context, raw, *, server_hostname):
        timeouts.append(raw.timeouts[-1])
        return raw

    monkeypatch.setattr(triage.ssl.SSLContext, "wrap_socket", wrap)
    client = triage._PinnedHTTPSConnection("docs.example.test", 443, [address()], 10.0)
    client.connect()
    assert timeouts == [1.0]
    client.close()


@pytest.mark.parametrize(
    "destination",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest",
        "http://private.example.test/",
    ],
)
def test_redirect_revalidates_and_never_connects_to_private_destination(
    monkeypatch, transport, destination
):
    def dns(host, port, **kwargs):
        return [address(PUBLIC if host == "public.example.test" else "127.0.0.1", port)]

    monkeypatch.setattr(triage.socket, "getaddrinfo", dns)
    transport[3].append(
        f"HTTP/1.1 302 Found\r\nLocation: {destination}\r\nContent-Length: 0\r\n\r\n".encode()
    )
    verdict, detail = triage.check_url("http://public.example.test/")
    assert verdict == "fail" and "non-public" in detail
    assert transport[0] == [(PUBLIC, 80)]


def test_each_public_redirect_uses_only_its_validated_socket_address(
    monkeypatch, transport
):
    calls = []

    def dns(host, port, **kwargs):
        calls.append(host)
        return [address(PUBLIC if host == "first.example.test" else "8.8.8.8", port)]

    monkeypatch.setattr(triage.socket, "getaddrinfo", dns)
    transport[3].append(
        b"HTTP/1.1 301 Moved\r\nLocation: http://second.example.test/new#anchor\r\nContent-Length: 0\r\n\r\n"
    )
    assert triage.check_url("http://first.example.test/") == ("pass", "HTTP 200")
    assert calls == ["first.example.test", "second.example.test"]
    assert transport[0] == [(PUBLIC, 80), ("8.8.8.8", 80)]
    assert b"Host: second.example.test" in transport[1][-1]


def test_redirect_limit_stops_before_another_resolution(monkeypatch, transport):
    calls = []

    def dns(host, port, **kwargs):
        calls.append(host)
        return [address(PUBLIC, port)]

    monkeypatch.setattr(triage.socket, "getaddrinfo", dns)
    transport[3].extend(
        [b"HTTP/1.1 302 Found\r\nLocation: /again\r\nContent-Length: 0\r\n\r\n"] * 4
    )
    verdict, detail = triage.check_url("http://public.example.test/")
    assert verdict == "fail" and "Too many redirects" in detail
    assert len(calls) == len(transport[0]) == triage.MAX_VERIFY_REDIRECTS + 1


@pytest.mark.parametrize("infos", [[], [address(PUBLIC), address("127.0.0.1")]])
def test_empty_or_mixed_private_dns_answers_are_refused_before_connection(
    monkeypatch, transport, infos
):
    monkeypatch.setattr(triage.socket, "getaddrinfo", lambda *args, **kwargs: infos)
    assert triage.check_url("http://public.example.test/")[0] == "skip"
    assert transport[0] == []


def test_credentials_and_non_http_urls_never_connect_or_leak_credentials(transport):
    for url in ("http://name:PRIVATE_CANARY@example.test/", "file:///etc/passwd"):
        verdict, detail = triage.check_url(url)
        assert verdict == "skip" and "PRIVATE_CANARY" not in detail
    assert transport[0] == []


def test_socket_retry_count_and_shared_timeout_are_bounded(monkeypatch, transport):
    monkeypatch.setattr(
        triage.socket, "getaddrinfo", lambda *args, **kwargs: [address()] * 20
    )

    def refuse(self, sockaddr):
        raise OSError("no route")

    monkeypatch.setattr(FakeSocket, "connect", refuse)
    assert triage.check_url("http://public.example.test/")[0] == "fail"
    assert len(transport[2]) == 8 and all(item.closed for item in transport[2])
    assert all(0 < item.timeouts[0] <= triage.VERIFY_TIMEOUT for item in transport[2])


@pytest.mark.parametrize(
    "status,verdict",
    [
        (200, "pass"),
        (204, "pass"),
        (404, "fail"),
        (410, "fail"),
        (403, "warn"),
        (429, "warn"),
        (500, "warn"),
    ],
)
def test_existing_http_status_verdicts_are_preserved(
    monkeypatch, transport, status, verdict
):
    monkeypatch.setattr(
        triage.socket, "getaddrinfo", lambda *args, **kwargs: [address()]
    )
    transport[3].append(
        f"HTTP/1.1 {status} Result\r\nContent-Length: 0\r\n\r\n".encode()
    )
    assert triage.check_url("http://public.example.test/")[0] == verdict
