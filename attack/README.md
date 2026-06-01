# Hack-the-planet kit

The lab Gold challenge says you're both predator and prey. This folder
has the predator side: scripts and instructions to point at a peer's
ProElev server and see how their defenses hold up. The matching
defenses live in the main backend and are documented in
`docs/database_design.md`.

> **Disclaimer.** Only run these against your own server or someone
> who explicitly invited you to attack theirs. Pointing this at random
> infrastructure is a crime in most countries.

---

## 1. JMeter — DDOS the login endpoint

`ddos.jmx` is an Apache JMeter test plan that fires 50 concurrent
threads × 200 iterations = **10,000 POSTs to `/auth/login`** with
random email addresses and a wrong password. With HTTPS turned on
and a self-signed cert, JMeter will refuse the connection until you
disable cert validation.

### one-time setup

1. Install JMeter 5.6+ from https://jmeter.apache.org/.
2. Open `attack/ddos.jmx` in JMeter.
3. In the **TestPlan → User Defined Variables**, change `HOST`,
   `PORT`, `SCHEME` to point at the target. For the lab demo:
   `HOST=192.168.x.y`, `PORT=8000`, `SCHEME=https`.
4. If the target uses a self-signed cert, run JMeter with
   `-Jhttps.use.cached.ssl.context=false` and add
   `-Jjavax.net.ssl.trustStoreType=Windows-ROOT` (Windows) or
   accept the cert error in the JMeter SSL Manager.

### running

Hit the green play button at the top, or from the command line:

```
jmeter -n -t ddos.jmx -l results.jtl
```

Watch the Summary Report panel — you should quickly see the
target's per-IP rate limit kick in (HTTP 429) followed by the login
throttle (HTTP 429 for any combination of IP + email seen too often).

### what defenses fire, in order

1. **Defense middleware rate limit, `/auth/*` bucket** — after 20
   requests in a 60s window from your IP, every further request is
   rejected with 429 + Retry-After.
2. **Login throttle** — even if you spread the load across IPs, hitting
   the same email with five bad passwords inside 2 minutes locks that
   (ip, email) pair for 5 minutes.
3. **Detector + auto-revoke** — if you fool the throttle by varying
   emails but you're somehow authenticated, the action-log detector
   notices the burst, scores the user, and after `BLOCK_THRESHOLD`
   points all of their sessions are revoked.

---

## 2. Wireshark — sniffing the network

Wireshark watches the raw packets going across the network adapter
your machine is on. Without HTTPS, a peer on the same LAN can see
every login email + password in plaintext. **Demonstrating this is
the whole point**: the defense is that ProElev only listens on HTTPS.

### one-time setup

1. Install Wireshark from https://www.wireshark.org/.
2. Pick the network interface that's actually on the lab/hotspot
   LAN (Wi-Fi adapter, usually).

### attack 1 — sniff a peer running over HTTP

1. Tell your peer to start the backend WITHOUT the `--ssl-keyfile`
   flags (regular HTTP).
2. In Wireshark, apply the display filter
   `tcp.port == 8000 && ip.host == 192.168.x.y`.
3. Right-click any captured packet → **Follow → HTTP stream**.
   You'll see the JSON body of `/auth/login` with the password in
   the clear.

### attack 2 — try the same against HTTPS

1. Have the peer restart the backend WITH the `--ssl-keyfile` and
   `--ssl-certfile` flags (HTTPS mode), see
   `src/backend/make_cert.py`.
2. Same Wireshark capture. The TCP stream is now opaque TLS,
   you can see the handshake (server certificate, cipher suite)
   but the bodies are encrypted.
3. Show the lab teacher that the password isn't visible — that's
   the encryption-in-transit defense.

### bonus — replay-attack protection

ProElev's JWT carries an `iat` and `jti`. Even if you captured a
plaintext token on the HTTP run, you can't replay it on the HTTPS
run because the server-side `Session` row is revoked after each
new login (and short-lived anyway — 30 minutes).

---

## 3. Other tools to try

A non-exhaustive list of things the lab teacher will recognize:

- **Burp Suite / OWASP ZAP** — intercepting proxy, lets you replay
  and tamper with requests. Try removing the `Authorization` header
  from `/admin/observations` and you'll get a clean 401.
- **sqlmap** — automated SQL injection. ProElev uses SQLAlchemy
  ORM so parameter binding is automatic; sqlmap won't find an
  injection point in the JSON request bodies, but it's a quick
  audit to show your peer.
- **hydra** — brute-force a login. The login throttle blocks this
  after five tries per (ip, email) pair; hydra will report most
  attempts as 429.
- **nmap** — port scan. The server only listens on 8000. nmap also
  detects the TLS handshake so it can fingerprint the cipher
  suite.
