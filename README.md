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

## Cleanup pass

Did a full line-by-line read-through of the file looking for inconsistencies rather than new features. Found two real things:

- **A real bug**: the Hysteria2 compatibility warning was written as `outputWarning.innerHTML = '...'` (overwrite) instead of `+=` (append). Harmless on its own, but if the device was set to Android/iOS *and* the parsed server was Hysteria2, this silently wiped out the "most apps don't use this file" caveat that had just been added right before it. Fixed to append like every other warning does.
- **Dead-weight JSON on Windows**: the `dns.hosts` bootstrap block was always included with three fixed entries, but with the default IP-form DNS servers (`https://1.1.1.1/dns-query`), none of those entries were ever actually referenced by anything — they were inert. Made this dynamic: it now only includes a `hosts` entry for a domain-named DoH hostname if that hostname is actually present in the configured DNS server list. Default output no longer carries unused bootstrap entries; customizing the DNS field to a domain-form endpoint (like `https://cloudflare-dns.com/dns-query`) now correctly produces exactly the one bootstrap entry needed for it — nothing more, nothing less.

Verified both with the exact scenario that exposed the first bug (Android device + Hysteria2 link — both warnings now show together), and confirmed the `hosts` block is absent by default and appears correctly scoped when needed.

## Device type: Windows, macOS, Linux, Android, iOS

An honest note before the feature list: since TUN mode was removed, the `config.json` itself barely differs across desktop OSes — a `mixed` SOCKS+HTTP inbound is identical cross-platform in xray-core. So "device type" mostly changes DNS structure and practical setup guidance, not some fictional per-OS JSON schema. Verified this by checking how real Android/iOS clients actually document their own import flow, rather than assuming.

- **Windows** — follows the structure of the config you uploaded: `dns.hosts` bootstraps well-known DoH hostnames (so resolving them doesn't depend on DNS that isn't working yet), plus a plain fast resolver scoped to `geosite:private` with `skipFallback`, ahead of the encrypted DoH catch-all. (Adapted to globally-neutral Cloudflare/Google IPs rather than the China-specific DNSPod resolver in the original — the *structure* is what's being followed, not a locale-specific server choice that wouldn't suit everyone.)
- **macOS / Linux** — the simpler flat DoH list (as before), plus a practical setup tip: `networksetup -setsocksfirewallproxy` for macOS, `export ALL_PROXY=socks5://...` for Linux.
- **Android / iOS — an honest caveat, not a fake JSON difference.** Real clients (v2rayNG, NekoBox, HiddifyNG, Shadowrocket, Streisand, Quantumult X) import the original share link or a subscription URL directly — they don't consume a raw xray-core `config.json` the way v2rayN does. Selecting either of these shows that plainly, rather than pretending this file is the normal workflow there. It's still generated correctly and is genuinely useful if you're running xray-core directly (e.g. via Termux on Android), just not for the mainstream app experience.

## New: warning for VLESS with no transport security on a public address

Read through xray-core's own VLESS docs page fully (not just search snippets this time) and found an explicit WARNING box: VLESS with no outer TLS/REALITY layer is only intended for a private/local peer, or when VLESS Encryption is configured — anything else sends traffic with zero transport-layer encryption. This tool now surfaces that as a warning when it applies: `security: none`, no VLESS Encryption string, and the server address isn't a private IP/`.local`/`.lan`/`localhost`. Correctly stays silent for private addresses, for links that do specify VLESS Encryption, and for anything using real TLS/REALITY — verified all four combinations explicitly.

Also confirmed while reading that page: the VLESS Encryption string format (`mlkem768x25519plus.native.0rtt.<padding-blocks>.<key>`) is exactly as complex as it looks, and this tool's approach of passing it through completely opaquely — never trying to parse, validate, or reconstruct it — is the correct one; xray-core's own docs recommend generating it via `xray vlessenc` rather than hand-building it, which is exactly what a hand-off/pass-through approach respects.

## "Private" now covers domains too, not just IPs

Re-reading the reference config once more turned up one clear thing still missing: it bypasses private/local traffic with **two** rules, not one — `geoip:private` for IPs and `geosite:private` for domains (router admin panels, local mDNS-style hostnames, etc.). This tool only had the IP rule. The "Route private/LAN traffic directly" checkbox now adds both together.

Deliberately *not* changed to match the reference: `routing.domainStrategy` stays `IPIfNonMatch` rather than the reference's `AsIs` — it gives the private-bypass rules a better chance of catching a domain that resolves to a private IP but isn't on the `geosite:private` list, which matters more now that domain-based bypass exists too, not less.

## Hysteria2: obfuscation and cert pinning were being silently dropped

Re-checked the actual canonical `hysteria2://` URI spec (v2.hysteria.network) — it defines `obfs`, `obfs-password`, `sni`, `insecure`, and `pinSHA256` as standard query params. This tool was only ever reading `sni`/`insecure`; `obfs`/`obfs-password`/`pinSHA256` were silently thrown away.

- **`pinSHA256`** now maps straight to `tlsSettings.pinnedPeerCertSha256` — simple, safe, standard.
- **`obfs`/`obfs-password`** (Salamander obfuscation) now maps to `hysteriaSettings.udpmasks`, xray-core's actual current field for this (confirmed via a real xray-core GitHub issue showing the correct shape — it's *not* a flat `obfs` field). **But** — that same issue (XTLS/Xray-core#5712) reports a currently-open, unresolved bug: xray-core's Salamander implementation can time out connecting to real Hysteria2 servers with obfuscation enabled, even with a correct password. Since silently dropping the obfuscation info would just produce a different, more confusing failure, it's included in the config, but the tool now shows a clear warning naming the specific issue when a link requests it — so a timeout has an actual explanation instead of being a mystery.

## Two more patterns adopted, plus an unrelated bug caught along the way

- **QUIC excluded from sniffing when it's blocked anyway.** If "Block QUIC" is on, `destOverride` no longer includes `"quic"` — matches the reference config exactly; there's nothing to gain sniffing traffic that gets blocked outright before the sniffed result would ever matter.
- **Explicit catch-all routing rule** (`port: "0-65535" → proxy`) added at the end of the rules array, instead of relying on the implicit "unmatched traffic falls to the first outbound" behavior. Same effect today, but doesn't silently break if outbounds are ever reordered later — matches the reference config's own explicit catch-all.
- **Unrelated bug found and fixed while testing:** a short (≤20 char) base64-encoded `method:password` in a SIP002 Shadowsocks link (`ss://BASE64@host:port`) was being rejected by a length heuristic meant for a different purpose (subscription-blob detection). Short passwords are completely valid, so this was a real, silent parse failure for some real-world links. Fixed by just trying the base64 decode directly and checking if it produced a sane result, instead of gatekeeping on string length first.

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
