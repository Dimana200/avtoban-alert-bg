"""Shared helpers: IPv4-only HTTP (GitHub runners have no IPv6 route) and distance."""
import json, math, socket, time, urllib.parse, urllib.request

_gai = socket.getaddrinfo
socket.getaddrinfo = lambda host, port, family=0, *a, **k: _gai(host, port, socket.AF_INET, *a, **k)

UA = "avtoban-alert-bg/1.0 (https://github.com/Dimana200/avtoban-alert-bg)"


def http(url, data=None, timeout=300, tries=3, raw=False):
    body = urllib.parse.urlencode(data).encode() if data else None
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
                return b if raw else json.loads(b)
        except Exception as e:  # noqa: BLE001 - retry any network/server error
            last = e
            print(f"   {url[:60]}: {e}", flush=True)
            time.sleep(15 * (i + 1))
    raise RuntimeError(f"failed: {last}")


def km(a, b):
    r = math.pi / 180
    x, y = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    h = math.sin(x / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(y / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))
