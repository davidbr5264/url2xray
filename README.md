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

## Single mixed inbound + QUIC blocking

Two changes adopted directly from the real v2rayN config analyzed above:

- **One `mixed` inbound instead of separate SOCKS/HTTP inbounds.** A `mixed` protocol inbound auto-detects whether an incoming connection is speaking SOCKS5 or HTTP CONNECT on the same port, so there's now a single "Port" field (default `10808`, matching the convention) instead of two, and the port-collision check that existed purely to guard against two inbounds sharing a port is gone — there's only one inbound now, so the problem it guarded against no longer exists.
- **"Block QUIC (UDP/443)" checkbox.** Adds a routing rule blocking UDP/443 outright, forcing browsers back to regular TCP+TLS. This is a real pattern used in production configs — sniffing and domain-based routing are more reliable against TLS ClientHello than against QUIC, so blocking QUIC outright sidesteps that gap entirely rather than trying to sniff it.

## Corrected against a real v2rayN config

A real, working config.json from v2rayN (a widely-used Windows xray-core client) surfaced two things worth fixing directly:

- **REALITY field reverted to `publicKey`.** Earlier in this project I switched to `password` based on doc wording alone. The actual commit history shows `password` was added as an *alias* of `publicKey`, not a replacement — both work, but `publicKey` is what v2rayN and essentially every real-world guide/tutorial actually generates. Matching the ecosystem's dominant convention matters more here than technically-newer-but-rarely-used naming.
- **Fixed a DNS bootstrap bug.** The default DNS servers included `https://dns.google/dns-query` — a DoH endpoint whose *own hostname* needs to be resolved before it can be reached, a circular dependency if it's ever actually needed. Switched to `https://8.8.8.8/dns-query` (same provider, IP-form host, no bootstrap problem) alongside `https://1.1.1.1/dns-query`.

Also confirmed real but not adopted for this "simple" tool: that config blocks UDP/443 to force QUIC back to regular TLS, uses a single `mixed` inbound (SOCKS+HTTP auto-detected on one port) instead of two separate ones, and uses a `dns.tag`+`inboundTag`-routing trick to send xray's own DNS queries through the proxy tunnel — though that last one had what looks like a rule-ordering mistake in the example itself (the relevant rules sat after a catch-all that would already have consumed everything).

## Schema notes (verified against xray-core's own docs)

- Outbounds use the current flat schema (no `vnext`/`servers` arrays).
- REALITY's client field is `password` (renamed from `publicKey`).
- `tcp`/`ws` are now `raw`/`websocket`; the old `http`/`h2` transport was removed in favor of `xhttp`.
- SOCKS/HTTP inbound auth uses `users`, not `accounts` — the wrong field name is silently ignored by xray-core at runtime rather than erroring.
- **TUN inbound settings are `name` + `MTU` only** — xray-core's own `proxy/tun/README.md` is explicit that there's no built-in addressing or routing. You have to configure routes yourself at the OS level after starting xray-core (`ip route` / `route add` depending on platform). This tripped up an earlier version of this tool badly enough to cause crashes — don't skip it.
