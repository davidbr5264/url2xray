#!/usr/bin/env python3
"""
url2xray.py — Convert vless:// vmess:// trojan:// ss:// share links into
a full Xray-core client config.json.

Matches the current Xray-core outbound schema (flat settings, streamSettings.method
instead of .network — see https://xtls.github.io/en/config/outbounds/ and
https://xtls.github.io/en/config/transport.html).

Usage:
    python url2xray.py "vless://uuid@host:port?...#remark" -o config.json
    python url2xray.py -f links.txt -o config.json --no-tun   (plain socks/http only)
"""

import argparse
import base64
import json
import sys
from urllib.parse import urlparse, parse_qs, unquote

# share-link "type=" values -> current Xray-core streamSettings.method
METHOD_MAP = {
    "tcp": "raw", "raw": "raw",
    "ws": "websocket", "websocket": "websocket",
    "grpc": "grpc",
    "kcp": "mkcp", "mkcp": "mkcp",
    "http": "xhttp", "xhttp": "xhttp",
    "httpupgrade": "httpupgrade",
    "quic": "raw",  # quic transport was removed; falls back to raw (will warn)
}

# XTLS flow is only valid on raw transport + tls/reality security
def flow_allowed(method: str, security: str) -> bool:
    return method == "raw" and security in ("tls", "reality")


def build_stream_settings(method_raw: str, security: str, q: dict, hostname: str) -> dict:
    method = METHOD_MAP.get(method_raw, "raw")
    stream = {"method": method, "security": security}

    if security == "reality":
        stream["realitySettings"] = {
            "fingerprint": q.get("fp", "random"),
            "publicKey": q.get("pbk", ""),
            "serverName": q.get("sni", hostname),
            "shortId": q.get("sid", ""),
            "show": False,
            "spiderX": unquote(q.get("spx", "")),
        }
    elif security == "tls":
        stream["tlsSettings"] = {
            "serverName": q.get("sni", hostname),
            "fingerprint": q.get("fp", "chrome"),
            "allowInsecure": q.get("allowInsecure", "0") == "1",
        }

    if method == "raw":
        stream["rawSettings"] = {"header": {"type": q.get("headerType", "none")}}
    elif method == "websocket":
        stream["wsSettings"] = {
            "path": unquote(q.get("path", "/")),
            "headers": {"Host": q.get("host", hostname)},
        }
    elif method == "grpc":
        stream["grpcSettings"] = {
            "serviceName": unquote(q.get("serviceName", "")),
            "multiMode": q.get("mode", "gun") == "multi",
        }
    elif method == "xhttp":
        stream["xhttpSettings"] = {
            "path": unquote(q.get("path", "/")),
            "host": q.get("host", hostname),
            "mode": q.get("mode", "auto"),
        }
    elif method == "httpupgrade":
        stream["httpupgradeSettings"] = {
            "path": unquote(q.get("path", "/")),
            "host": q.get("host", hostname),
        }
    elif method == "mkcp":
        stream["kcpSettings"] = {"header": {"type": q.get("headerType", "none")}}

    return stream


def b64pad(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def parse_vless(link: str) -> dict:
    u = urlparse(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    security = q.get("security", "none")
    method_raw = q.get("type", "tcp")
    stream = build_stream_settings(method_raw, security, q, u.hostname)

    settings = {
        "address": u.hostname,
        "port": u.port,
        "id": unquote(u.username),
        "encryption": q.get("encryption", "none"),
        "level": 0,
    }
    flow = q.get("flow", "")
    if flow and flow_allowed(stream["method"], security):
        settings["flow"] = flow

    return {"protocol": "vless", "tag": "proxy", "streamSettings": stream, "settings": settings}


def parse_vmess(link: str) -> dict:
    raw = link[len("vmess://"):]
    data = json.loads(base64.b64decode(b64pad(raw)))
    net = data.get("net", "tcp")
    tls = data.get("tls", "")
    security = "tls" if tls == "tls" else "none"

    # Reconstruct a query-like dict from the vmess JSON fields so build_stream_settings
    # can reuse the same logic
    q = {
        "path": data.get("path", "/"),
        "host": data.get("host", data.get("sni", "")),
        "headerType": data.get("type", "none"),
        "serviceName": data.get("path", ""),
        "mode": data.get("mode", "gun"),
        "sni": data.get("sni", data.get("host", "")),
        "fp": data.get("fp", "chrome"),
    }
    stream = build_stream_settings(net, security, q, data.get("add", ""))

    settings = {
        "address": data["add"],
        "port": int(data["port"]),
        "id": data["id"],
        "security": data.get("scy", "auto"),  # cipher, not TLS — vmess-specific field name
        "level": 0,
    }
    return {"protocol": "vmess", "tag": "proxy", "streamSettings": stream, "settings": settings}


def parse_trojan(link: str) -> dict:
    u = urlparse(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    security = q.get("security", "tls")
    method_raw = q.get("type", "tcp")
    stream = build_stream_settings(method_raw, security, q, u.hostname)

    settings = {
        "address": u.hostname,
        "port": u.port,
        "password": unquote(u.username),
        "level": 0,
    }
    return {"protocol": "trojan", "tag": "proxy", "streamSettings": stream, "settings": settings}


def parse_ss(link: str) -> dict:
    raw = link[len("ss://"):]
    frag = ""
    if "#" in raw:
        raw, frag = raw.split("#", 1)

    if "@" in raw:
        userinfo, hostport = raw.split("@", 1)
        try:
            userinfo = base64.b64decode(b64pad(userinfo)).decode()
        except Exception:
            userinfo = unquote(userinfo)
        method, password = userinfo.split(":", 1)
        host, port = hostport.rsplit(":", 1)
        port = port.split("?")[0].split("/")[0]
    else:
        decoded = base64.b64decode(b64pad(raw)).decode()
        method_pw, hostport = decoded.split("@", 1)
        method, password = method_pw.split(":", 1)
        host, port = hostport.rsplit(":", 1)

    return {
        "protocol": "shadowsocks", "tag": "proxy",
        "settings": {
            "address": host, "port": int(port),
            "method": method, "password": password, "level": 0,
        },
    }


PARSERS = {"vless": parse_vless, "vmess": parse_vmess, "trojan": parse_trojan, "ss": parse_ss}


def parse_link(link: str) -> dict:
    link = link.strip()
    scheme = link.split("://", 1)[0].lower()
    if scheme not in PARSERS:
        raise ValueError(f"Unsupported scheme: {scheme}")
    return PARSERS[scheme](link)


def build_config(outbounds: list, extra_direct_domains=None, use_tun=True) -> dict:
    extra_direct_domains = extra_direct_domains or []

    inbounds = []
    if use_tun:
        inbounds.append({
            "tag": "tun-in", "port": 0, "protocol": "tun",
            "settings": {
                "name": "xray0", "mtu": 1500, "gateway": ["10.10.0.1/24"],
                "dns": ["8.8.8.8"], "autoSystemRoutingTable": ["0.0.0.0/0"],
                "autoOutboundsInterface": "auto",
            },
            "sniffing": {"destOverride": ["http", "tls", "quic", "fakedns"], "enabled": True},
        })
    inbounds += [
        {
            "port": 10808, "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True, "userLevel": 8},
            "sniffing": {"destOverride": ["http", "tls", "quic", "fakedns"], "enabled": True},
            "tag": "socks",
        },
        {"port": 10809, "protocol": "http", "settings": {"userLevel": 8}, "tag": "http"},
    ]

    return {
        "dns": {
            "queryStrategy": "UseIP",
            "servers": [{"address": "8.8.8.8", "skipFallback": False}],
            "tag": "dns_out",
        },
        "inbounds": inbounds,
        "log": {"loglevel": "warning"},
        "outbounds": outbounds + [
            {"protocol": "freedom", "settings": {"domainStrategy": "AsIs", "noises": [], "redirect": ""}, "tag": "direct"},
            {"protocol": "blackhole", "settings": {"response": {"type": "http"}}, "tag": "block"},
        ],
        "policy": {
            "levels": {"8": {"connIdle": 300, "downlinkOnly": 1, "handshake": 4, "uplinkOnly": 1}},
            "system": {"statsOutboundDownlink": True, "statsOutboundUplink": True},
        },
        "remarks": "Generated_by_url2xray",
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"ip": ["geoip:private"], "outboundTag": "direct", "type": "field"},
                {"domain": ["geosite:private"] + extra_direct_domains, "outboundTag": "direct", "type": "field"},
                {"network": "tcp,udp", "outboundTag": "proxy", "type": "field"},
            ],
        },
        "stats": {},
    }


def main():
    ap = argparse.ArgumentParser(description="Convert proxy share links to an Xray-core config")
    ap.add_argument("link", nargs="?", help="A single share link (vless/vmess/trojan/ss)")
    ap.add_argument("-f", "--file", help="Path to a text file with one link per line")
    ap.add_argument("-o", "--output", default="config.json", help="Output config path")
    ap.add_argument("-d", "--direct-domain", action="append", default=[],
                     help="Domain to route directly (bypass proxy). Can be repeated.")
    ap.add_argument("--no-tun", action="store_true",
                     help="Skip the TUN inbound — generate a plain socks(10808)/http(10809) config "
                          "that needs no admin rights.")
    args = ap.parse_args()

    links = []
    if args.link:
        links.append(args.link)
    if args.file:
        with open(args.file) as fh:
            links.extend(l.strip() for l in fh if l.strip() and not l.startswith("#"))
    if not links:
        ap.error("Provide a link as an argument or via --file")

    outbounds = []
    for i, link in enumerate(links):
        try:
            ob = parse_link(link)
        except Exception as e:
            print(f"Warning: skipping link #{i+1} ({e})", file=sys.stderr)
            continue
        if i > 0:
            ob["tag"] = f"proxy-{i}"
        outbounds.append(ob)

    if not outbounds:
        print("Error: no valid links parsed.", file=sys.stderr)
        sys.exit(1)

    config = build_config(outbounds, extra_direct_domains=args.direct_domain, use_tun=not args.no_tun)

    with open(args.output, "w") as fh:
        json.dump(config, fh, indent=2)

    mode = "socks/http only (no admin needed)" if args.no_tun else "TUN + socks/http"
    print(f"Wrote {args.output} [{mode}] with {len(outbounds)} outbound(s): "
          f"{', '.join(o['tag'] for o in outbounds)}")


if __name__ == "__main__":
    main()
