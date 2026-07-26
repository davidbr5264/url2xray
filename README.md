# xray-core Config Generator

One file, `index.html`. No build step, no dependencies beyond a Google Fonts import. Paste a link, pick a server, get a config.json for a local SOCKS+HTTP proxy.

## Deploy to Cloudflare Pages

Dashboard → Workers & Pages → Create → Pages → **Upload assets** → upload `index.html` → Deploy. Framework preset: None. No build command needed.

Or via Wrangler: `wrangler pages deploy . --project-name=xray-config-gen` (run from this folder).

## What it does

- Parses `vless://`, `vmess://`, `trojan://`, `ss://`, `hysteria2://`/`hy2://` links (single links, multiple lines, or a base64 subscription blob). `tuic://` links are rejected with a clear message — xray-core has no TUIC outbound.
- Generates a current-schema xray-core config for a local SOCKS+HTTP proxy (TUN mode removed for now — see below).
- Transports: raw/tcp, websocket, grpc, httpupgrade, xhttp, mkcp, quic. Security: none, tls, REALITY.
- Options: listen on localhost or the LAN, optional username/password auth, bypass private/LAN IPs, block ad/tracker domains, direct-domain overrides, DNS servers (defaults to DNS-over-HTTPS, not plaintext), log level.

## TUN mode: removed for now

TUN mode (and the platform-specific interface-naming logic from the last round) has been fully removed — SOCKS+HTTP is the only inbound this tool generates right now. We'll rebuild it deliberately later rather than leave it half-attached. Nothing else changed; parsing, direct domains, and LAN access all work exactly as before.

For whenever it comes back: the JSON schema was already confirmed correct (`{ name, MTU }` only — xray-core's own `proxy/tun/README.md` is explicit that no gateway/dns/auto-route fields exist), and interface naming genuinely differs by OS — free-form on Linux/Windows, `utunN` required on macOS, `tunN` required on FreeBSD. Worth re-verifying against the docs fresh rather than assuming this is still current by the time it's picked back up.

## LAN access

A "Listen address" option switches the SOCKS/HTTP inbounds from `127.0.0.1` (this device only) to `0.0.0.0`, so other devices on your LAN can use the proxy. Pairs with an optional username/password gate (uses the correct `users` field — not `accounts`, a real xray-core pitfall where the wrong field name is silently ignored at runtime rather than erroring). Generation blocks if auth is required with an empty password, and warns if you open it to the LAN without auth.

## Direct domains

A "Direct domains" field lets you list domains (or `geosite:`/`domain:`/`full:`/`keyword:`/`regexp:` matchers) that should always bypass the proxy and go straight out — one per line or comma-separated. Full URLs like `https://example.com/path` are auto-cleaned to just the hostname, since routing matches against sniffed SNI/Host values, which never include a scheme or path.

## What it deliberately doesn't do

This is a rebuild after the previous version accumulated a lot of feature surface (mux, fragment, cert pinning, ECH, custom domain routing, fingerprint overrides, round-trip import, pre-export validation, per-OS TUN routing commands, a committed test suite). All of that got cut in favor of doing the core job well. If you need any of it, the generated JSON is a normal xray-core config — hand-edit it, or ask for a specific feature to be added back deliberately rather than by default.

## Schema notes (verified against xray-core's own docs)

- Outbounds use the current flat schema (no `vnext`/`servers` arrays).
- REALITY's client field is `password` (renamed from `publicKey`).
- `tcp`/`ws` are now `raw`/`websocket`; the old `http`/`h2` transport was removed in favor of `xhttp`.
- SOCKS/HTTP inbound auth uses `users`, not `accounts` — the wrong field name is silently ignored by xray-core at runtime rather than erroring.
- **TUN inbound settings are `name` + `MTU` only** — xray-core's own `proxy/tun/README.md` is explicit that there's no built-in addressing or routing. You have to configure routes yourself at the OS level after starting xray-core (`ip route` / `route add` depending on platform). This tripped up an earlier version of this tool badly enough to cause crashes — don't skip it.
