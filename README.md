# xray-core Config Generator

A single static `index.html` — no build step, no backend, no dependencies fetched at runtime beyond a Google Fonts stylesheet. Everything (parsing links, building JSON) runs client-side in the browser, so proxy links and keys never leave the user's machine.

## Deploy to Cloudflare Pages

**Option A — dashboard, no git:**
1. Cloudflare dashboard → Workers & Pages → Create → Pages → **Upload assets**.
2. Upload `index.html` (drag the file or the folder containing it).
3. Deploy. Framework preset: "None" / static. No build command, no output directory needed beyond the root.

**Option B — Wrangler CLI:**
```bash
npm install -g wrangler
wrangler pages deploy . --project-name=xray-config-gen
```
(run from this folder — it will publish `index.html` as-is)

**Option C — connect a GitHub repo:**
Push this folder to a repo, then in Pages choose "Connect to Git", set build command to empty and output directory to `/`.

## What it supports

- Parses `vless://`, `vmess://`, `trojan://`, `ss://`, `hysteria2://`/`hy2://`, `tuic://` links (single links or a base64 subscription blob).
- Transports: tcp (raw/http-obfs), ws, grpc, http/h2, httpupgrade, xhttp, kcp, quic; security: none, tls, REALITY.
- Two inbound modes:
  - **SOCKS + HTTP** — standard local proxy, works with any xray-core version.
  - **TUN** — uses xray-core's native `tun` inbound protocol (added in recent xray-core releases). Requires elevated/admin privileges to run, and a fairly current xray-core build.
- `tuic://` links are parsed and shown, but config generation is blocked for them — **xray-core does not implement a TUIC outbound**. Use sing-box for those.
- Hysteria2 (`hysteria` outbound in xray-core) is generated, but flagged with a caveat: xray-core's Hysteria2 support has had version-to-version bugs upstream, so verify against your installed release.

## Changelog — updated against current xray-core config schema

Checked against the current official docs (xtls.github.io) and recent xray-core changelogs/issues, a few real schema changes went in:

- **Outbound settings are now flat, single-endpoint objects.** VLESS/VMess/Trojan/Shadowsocks outbounds no longer use the old `vnext`/`servers` arrays — current xray-core takes `address`/`port`/... directly under `settings`, one endpoint per outbound (multi-server setups are expected to use routing/balancers instead). Updated all four builders.
- **REALITY's client-side field was renamed** `publicKey` → `password` (still the same x25519 public key value — just a name change to avoid implying it's safe to publish). Fixed.
- **VMess dropped AlterId entirely.** No more `aid`/`alterId` in the outbound — removed.
- **VLESS `encryption` is now read from the link** instead of hardcoded to `"none"` — newer links can carry a real VLESS Encryption string (post-quantum ML-KEM-768/X25519 key exchange), which is passed through as-is with an on-screen note to double-check it matches the server.
- **`tcp`/`ws` transports renamed** to `raw`/`websocket` in current config (old names still work as aliases in the Go parser, but the generator now emits the current names).
- **The old `http`/`h2` transport was removed from xray-core entirely** — links using it are now auto-migrated to XHTTP (its documented direct replacement) with an on-screen note.
- **mKCP dropped its `header`/`seed` obfuscation fields** (moved to a separate FinalMask layer) — removed from the generator since there's no established link convention for FinalMask yet.
- **TLS `allowInsecure` is deprecated** in favor of `pinnedPeerCertSha256`, though still documented as functional — only emitted when a link explicitly requests it, with a warning that newer builds may reject it.
- **Hysteria2 outbound's `settings` object is much leaner** than previously modeled — just `version`/`address`/`port`; auth and TLS behavior live entirely in `streamSettings`.

## Fixed: SOCKS/HTTP inbound auth used the wrong field name

Re-checked every protocol/feature against the current docs again, and found one real, confirmed bug: the inbound-auth feature (added a few turns back) wrote credentials into an `"accounts"` array. **The actual xray-core field is `"users"`.** `"accounts"` isn't rejected — it just parses fine and is silently ignored at runtime, so the inbound stays wide open with no auth at all. This is a known community pitfall (see XTLS/Xray-core#4487 and #5943, where people hit exactly this and reported auth "just doesn't work"). Fixed for both the SOCKS and HTTP inbounds.

Everything else in this pass re-verified clean: outbound flat-schema for VLESS/VMess/Trojan/Shadowsocks, the Hysteria2 outbound's lean `settings` object, TUN's exact field set (independently re-confirmed against three live examples, including one showing a broken config from using uppercase `"MTU"` instead of `mtu`), the `network: "tcp,udp"` string format for the DNS-leak routing rule, and TUIC's continued absence from both the inbound and outbound protocol lists — so blocking it was and still is correct.

## Security hardening: DNS leak protection + cert pinning/ECH

- **DNS servers now default to DoH** (`https://1.1.1.1/dns-query, https://dns.google/dns-query`) instead of plaintext UDP. If you switch to a plaintext entry, the generated output flags it as an observable/tamperable leak.
- **"Block direct port-53 DNS" toggle** (on by default) adds a routing rule blocking raw UDP/TCP port 53 outside `geoip:private`, so an app or the OS can't quietly bypass xray's configured resolver and leak plaintext DNS queries around the tunnel.
- **Certificate pinning** (`pinnedPeerCertSha256`) — pin a server's exact leaf-cert hash instead of (or alongside) trusting the CA chain. Get the hash with `xray tls hash --cert <cert.pem>`, `xray tls ping <host:port>`, or `openssl x509 -noout -fingerprint -sha256 -in cert.pem`. Note: this field changed from a JSON array to a single tilde-separated string in a recent xray-core release — the generator emits it that way.
- **ECH (Encrypted Client Hello)** (`echConfigList`) — hides the SNI from network-level observers, which REALITY's camouflage doesn't fully do. Accepts either a fixed ECHConfig string or a DNS-query directive like `https://1.1.1.1/dns-query`.
- Both cert pinning and ECH only apply where `tlsSettings` actually exists (plain TLS security, and Hysteria2's TLS layer) — not REALITY, which has its own mechanism. The tool warns rather than silently dropping the fields if you set them on an incompatible server.

## New: Round-trip config.json import

Step 1 now has a collapsible "Import an existing config.json instead" section. Paste back a config this tool generated (or any hand-written xray-core config using vless/vmess/trojan/shadowsocks/hysteria), and it reconstructs:

- The active server (picks the outbound tagged `proxy`, or the first non-infrastructure outbound) — protocol, address, port, credentials, transport, security, and TLS/REALITY fields.
- Inbound mode (SOCKS vs TUN) and all its settings, including listen address, UDP toggle, and auth.
- Every advanced option: sniffing, mux, fragment, cert pinning, ECH, DNS servers/strategy/cache, routing strategy, custom domain rules, ad-block, DNS leak-block.

Limitations:
- Only round-trips a single active proxy outbound — configs with balancers or multiple proxy outbounds get a note that extras were skipped.
- `wireguard`/`socks`/`http`-as-outbound (proxy chaining) aren't round-trippable, since they're not link protocols this tool speaks in the first place.
- A global fingerprint override isn't reconstructed as an override — the fingerprint is already baked into the imported server's own transport settings, which has the same net effect.

Verified with an actual round-trip test: generate a fully-loaded config (SOCKS+auth+fragment+custom domains+DNS strategy, and separately TUN+mux+cert-pinning+ECH+FakeDNS), import it into a fresh session, regenerate, and diff — both came back byte-for-byte identical on every structural field checked. Also checked the error paths (invalid JSON, missing outbounds, unsupported protocol, empty input) all fail with a clear message instead of breaking.

## Inbound access & TLS/REALITY fingerprint controls

- **Listen address** — SOCKS/HTTP inbounds default to `127.0.0.1`; can be switched to `0.0.0.0` to serve your whole LAN. The tool warns (live in the UI, and again in the generated config's notes) if you pick LAN-wide without also turning on inbound auth.
- **UDP on/off** for the SOCKS inbound, as an explicit switch instead of always-on.
- **Client fingerprint override** — forces a specific uTLS fingerprint (`chrome`/`firefox`/`safari`/`ios`/`android`/`edge`/`random`/`randomized`) on both `tlsSettings.fingerprint` and `realitySettings.fingerprint`, regardless of what an individual link specifies. Left blank, it falls through to each link's own value as before.

## Customization options (Advanced panel)

All grounded in current xray-core docs/schema:

- **Sniffing** — enable/disable, `routeOnly` (route by sniffed SNI but still proxy to the original IP), and FakeDNS (`destOverride: ["fakedns"]` + a `"fakedns"` DNS server entry — handy for domain-based routing under TUN without a real lookup first).
- **Inbound auth** — switches the local SOCKS/HTTP inbounds from open (`noauth`) to a username/password (`accounts` array), for when the local proxy isn't strictly localhost-only.
- **Mux** — `enabled`/`concurrency`/`xudpProxyUDP443` on the proxy outbound. The tool warns when the selected server uses XTLS Vision flow, since Mux is generally not recommended alongside Vision (it breaks Vision's direct TCP splicing).
- **Fragment** — TLS ClientHello fragmentation (`packets`/`length`/`interval`) on the direct/freedom outbound, for censorship circumvention on the dial-out to your own server.
- **DNS query strategy & cache**, **routing `domainStrategy`**, and **Freedom outbound `domainStrategy`** — exposed as selects with the real enum values from the docs (`AsIs`/`UseIP`/`UseIPv4`/`UseIPv6`/`ForceIP`/etc., which differ slightly between routing and freedom).
- **Custom domain routing** — free-text lists (accepting `domain:`/`geosite:`/plain domains, one per line) to always force via proxy or always send direct, layered in ahead of the ad-block rule.

## Fixed: "Always direct domains" silently not matching

Root-caused via the official docs' explicit note that domain-based routing depends entirely on sniffing recovering a domain from raw traffic — if xray only ever sees an IP, domain rules can never match, no matter how they're written. Two concrete UI bugs made that easy to trigger by accident:

- **Full URLs weren't cleaned up.** Pasting `https://example.com/browse` (very natural, since that's what's in the address bar) put the literal string `https://example.com/browse` into the rule — which never appears in a sniffed SNI/Host value (those are bare hostnames only), so the rule silently never fired. Now stripped to `example.com` automatically, and left untouched if it already uses one of xray's own prefixes (`domain:`/`full:`/`keyword:`/`regexp:`/`geosite:`).
- **Inconsistent separator.** The DNS-servers field above it uses commas; the domain lists only accepted newlines, so a comma-pasted list became one unmatched blob. Both fields now accept comma **or** newline.

Also added: a live preview under each custom-domain field showing exactly what was parsed (so this stays visible instead of silently failing again), and an explicit warning in the generated output if sniffing is off while custom domain rules are set, since in that combination the rules are guaranteed to do nothing.

## Notes / known limits

- Only a single active outbound is generated at a time — no multi-server load balancing/failover config.
- Shadowsocks plugins (obfs, v2ray-plugin, etc.) aren't parsed — plain SS only.
- Always sanity-check the generated config against the xray-core version you're actually deploying; inbound/outbound schemas (especially `tun` and `hysteria`) have changed across releases.
