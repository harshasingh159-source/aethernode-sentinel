"""Read the connected-device list from your router's admin interface.

Supported: Nokia home routers that use the "web_whw" web app (Nokia WiFi Beacon
family and Nokia ONT gateways, as shipped by many ISPs).

Login, as the router's own web page does it:
  1. POST login_web_app.cgi?nonce  -> nonce, randomKey, RSA public key
  2. Build the form (username, password, nonce, a random AES key/iv), AES-128-CBC
     encrypt it, RSA-encrypt the AES key, POST login_web_app.cgi
  3. The router returns sid + token and sets a session cookie
Then GET dashboard_device_status_web_app.cgi gives every device it knows about.
We log out after every poll so we never hold the router's admin session.
"""
import base64
import ipaddress
import os
import platform
import re
import subprocess
import warnings
from urllib.parse import quote

import requests
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key


class RouterError(Exception):
    pass


class AuthError(RouterError):
    """Credentials were rejected: stop retrying so we don't trigger the router's lockout."""


def default_gateway():
    """Best-effort IPv4 default gateway (usually your router)."""
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True, text=True,
                                 timeout=5, creationflags=0x08000000).stdout
            m = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out, re.M)
        else:
            out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _esc(b64):
    """The router's 'base64url_escape': + / = become - _ ."""
    return b64.replace("+", "-").replace("/", "_").replace("=", ".")


def _pem(key):
    """The router sends the PEM on one line; re-wrap it so it parses."""
    body = re.sub(r"-----(BEGIN|END) PUBLIC KEY-----|\s", "", key)
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{lines}\n-----END PUBLIC KEY-----\n".encode()


def encrypt_form(form, pubkey, key=None, iv=None):
    """Encrypt a login form the way the router's crypto_page.encrypt_post_data does."""
    key, iv = key or os.urandom(16), iv or os.urandom(16)
    padder = padding.PKCS7(128).padder()
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = enc.update(padder.update(form.encode()) + padder.finalize()) + enc.finalize()
    secret = f"{base64.b64encode(key).decode()} {base64.b64encode(iv).decode()}".encode()
    ck = load_pem_public_key(_pem(pubkey)).encrypt(secret, rsa_padding.PKCS1v15())
    return "encrypted=1&ct={}&ck={}".format(
        base64.urlsafe_b64encode(ct).decode().rstrip("="),
        _esc(base64.b64encode(ck).decode()),
    )


def parse_json(raw, errors=None):
    """Parse a router reply. Router CGIs often emit sloppy JSON, so repair the usual mistakes:
    BOM / anti-XSSI prefix, trailing commas, invalid escapes like \\', empty values,
    missing commas between objects, and junk after the JSON. Failure details go to `errors`."""
    import json
    text = raw.decode("utf-8", errors="replace").lstrip("﻿").strip()
    text = re.sub(r"^\)\]\}',?\s*", "", text)  # Angular-style anti-XSSI prefix
    if text and text[0] not in "{[":
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if 0 < start < 200:  # e.g. a short preamble before the JSON
            text = text[start:]
    if not text or text[0] not in "{[":
        return None

    repairs = [
        lambda t: t,
        lambda t: re.sub(r",\s*([}\]])", r"\1", t),            # trailing commas
        lambda t: re.sub(r'\\([^"\\/bfnrtu])', r"\1", t),      # invalid escapes like \'
        lambda t: re.sub(r":\s*(?=[,}\]])", ": null", t),      # empty values
        lambda t: re.sub(r"}\s*{", "},{", t),                  # missing commas between objects
        lambda t: re.sub(r"([\[{])\s*,", r"\1", t),            # leading comma: [ ,{...}
        lambda t: re.sub(r",(\s*,)+", ",", t),                 # doubled commas: a,,b
    ]
    decoder = json.JSONDecoder(strict=False)
    err = None
    for fix in repairs:  # each repair builds on the previous ones
        text = fix(text)
        try:
            value, _end = decoder.raw_decode(text)  # ignores junk after the JSON value
            return value
        except ValueError as e:
            err = e
    if errors is not None and err is not None:
        pos = getattr(err, "pos", 0)
        ctx = re.sub(r"\s+", " ", text[max(0, pos - 50):pos + 30])
        errors.append(f"{getattr(err, 'msg', err)} at character {pos}: ...{ctx}...")
    return None


def describe_shape(data):
    """Section and field names only (no values), to diagnose an unfamiliar router layout."""
    parts = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                first = next((x for x in v if isinstance(x, dict)), {})
                parts.append(f"{k}[{len(v)}]({', '.join(list(first)[:12])})")
            elif isinstance(v, dict):
                parts.append(f"{k}{{{', '.join(list(v)[:12])}}}")
            else:
                parts.append(k)
    return "; ".join(parts)[:900] or type(data).__name__


def layout_summary(data, devices):
    """Counts and field names only (no names/MACs/IPs): enough to check the mapping is right."""
    sections = {}

    def walk(node, path, depth):
        if depth > 4:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k, depth + 1)
        elif isinstance(node, list) and any(isinstance(e, dict) for e in node):
            rows = [e for e in node if isinstance(e, dict)]
            sections[path] = {
                "entries": len(rows),
                "with_mac": sum(1 for e in rows if e.get("MACAddress")),
                "with_ip": sum(1 for e in rows if e.get("IPAddress")),
                "active": sum(1 for e in rows if str(e.get("Active")) == "1"),
                "fields": sorted({f for e in rows for f in e})[:30],
            }

    walk(data, "", 0)
    return {"sections": sections, "devices": len(devices),
            "active_devices": sum(1 for d in devices if d["active"]),
            "with_ip": sum(1 for d in devices if d.get("ip"))}


def _real_name(name):
    """Routers fill nameless hosts with placeholders like 'Unknown_0a:11:22:33:44:05' or '*'."""
    return bool(name) and str(name).strip() not in ("*", "") and not str(name).strip().lower().startswith("unknown")


def parse_devices(data):
    """Collect every host from the status JSON.

    Some firmwares split it: entries *with* a MACAddress (often a history of every device
    ever seen) and live status entries (device_cfg: HostName, Active, InterfaceType, IP)
    *without* one. Live entries are matched to MAC entries by device name.
    """
    found = {}
    status = []  # live entries that carry no MAC

    def walk(node, section):
        if isinstance(node, dict):
            mac = node.get("MACAddress")
            if mac and not any(node.get(k) not in (None, "") for k in
                               ("HostName", "HostAlias", "IPAddress", "Active", "InterfaceType")):
                mac = None  # the router's own ports/radios (e.g. lan_ether) also carry MACs: not hosts
            if not mac and "Active" in node and (node.get("HostName") or node.get("HostAlias")):
                status.append(node)
            if isinstance(mac, str) and re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac.strip()):
                mac = mac.strip().lower().replace("-", ":")
                d = found.setdefault(mac, {"mac": mac})
                name = node.get("HostAlias") or node.get("X_ALU_COM_HostAlias") or node.get("HostName")
                if _real_name(name) and not d.get("name"):
                    d["name"] = str(name).strip()
                if _real_name(node.get("HostName")) and not d.get("hostname"):
                    d["hostname"] = str(node["HostName"]).strip()
                ip = node.get("IPAddress") or node.get("IPv4Address")
                if ip and not d.get("ip"):
                    try:
                        ipaddress.ip_address(ip)
                        d["ip"] = ip
                    except ValueError:
                        pass
                if "Active" in node:
                    d["active"] = str(node["Active"]).lower() in ("1", "true", "yes", "online")
                    d["status_from_mac"] = True
                for key, out in (("InterfaceType", "connection"), ("AddressSource", "address_source"),
                                 ("DeviceType", "device_type"), ("X_ASB_COM_DeviceType", "device_type")):
                    if node.get(key) and not d.get(out):
                        d[out] = str(node[key])
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                walk(item, section)

    walk(data, None)

    if status:
        by_name = {}
        for d in found.values():
            for n in {d.get("name"), d.get("hostname")} - {None}:
                by_name.setdefault(n.strip().lower(), []).append(d)
        for node in status:
            names = {str(node.get(k) or "").strip().lower() for k in ("HostAlias", "HostName")} - {""}
            matches = {id(d): d for n in names for d in by_name.get(n, [])}
            if len(matches) != 1:
                continue  # unknown or ambiguous name (e.g. several "iPhone"s): don't guess
            d = next(iter(matches.values()))
            if d.get("status_from_mac"):
                continue  # a source that lists the MAC itself is more reliable than a name match
            d["active"] = str(node.get("Active")).lower() in ("1", "true", "yes", "online")
            ip = node.get("IPAddress") or node.get("IPv4Address")
            if ip and not d.get("ip"):
                try:
                    ipaddress.ip_address(ip)
                    d["ip"] = ip
                except ValueError:
                    pass
            if node.get("InterfaceType") and not d.get("connection"):
                d["connection"] = str(node["InterfaceType"])

    for d in found.values():
        d.setdefault("active", bool(d.get("ip")))
    return sorted(found.values(), key=lambda d: (not d["active"], (d.get("name") or "~").lower()))


class NokiaRouter:
    kind = "Nokia"
    # (label, CGI) pairs read after the dashboard: "connected devices" and the LAN host table
    EXTRA_SOURCES = (("clients", "device_home_nw_client_status_web_app.cgi"),
                     ("lan", "lan_status_web_app.cgi?lan"))

    def __init__(self, url, username, password, timeout=15):
        url = url.strip().rstrip("/")
        if not re.match(r"^https?://", url):
            url = "https://" + url
        self.url, self.username, self.password, self.timeout = url, username, password, timeout
        self.session = requests.Session()
        self.session.verify = False  # home routers use self-signed certificates
        # Look like the router's own web page: its CGIs check the Referer (the page sets
        # <meta name="referrer" content="origin"> for exactly this) and expect a browser.
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{self.url}/",
            "Origin": self.url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        })
        self.last = {}  # status/content-type/location of the last response, for error messages

    # overridable in tests
    def _request(self, method, path, data=None):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # InsecureRequestWarning for the self-signed cert
            try:
                # a redirect means "not logged in": report it instead of following it to the login page
                r = self.session.request(method, f"{self.url}/{path}", data=data,
                                         timeout=self.timeout, allow_redirects=False)
            except requests.RequestException as e:
                raise RouterError(f"Can't reach the router at {self.url} ({e.__class__.__name__})") from e
        preview = re.sub(r"\s+", " ", r.content[:120].decode("utf-8", errors="replace"))
        self.last = {"status": r.status_code, "type": r.headers.get("Content-Type", ""),
                     "location": r.headers.get("Location"), "size": len(r.content), "preview": preview}
        self.last["json_errors"] = []
        return parse_json(r.content, self.last["json_errors"])

    def login(self):
        info = self._request("POST", "login_web_app.cgi?nonce", f"userName={quote(self.username)}")
        if not isinstance(info, dict) or not info.get("nonce") or not info.get("pubkey"):
            raise RouterError("This doesn't look like a supported Nokia router (no login nonce).")
        form = (f"userhash={self.username}&RandomKeyhash={info.get('randomKey', '')}"
                f"&response={quote(self.password, safe=chr(39) + '-_.!~*()')}"
                f"&nonce={_esc(info['nonce'])}"
                f"&enckey={_esc(base64.b64encode(os.urandom(16)).decode())}"
                f"&enciv={_esc(base64.b64encode(os.urandom(16)).decode())}"
                f"&nohash=1&hPassword=undefined")
        res = self._request("POST", "login_web_app.cgi", encrypt_form(form, info["pubkey"]))
        if not isinstance(res, dict):
            raise RouterError("Router gave an unexpected login response.")
        if res.get("is_hacker"):
            raise AuthError("Router has temporarily locked logins after failed attempts. Wait a few minutes.")
        if res.get("result") != 0 or not res.get("sid"):
            raise AuthError(res.get("error_msg") or "Login failed: check the username and password.")
        if "sid" not in self.session.cookies:
            # The session lives in a "sid" cookie; set it ourselves if the router only put it in the JSON.
            host = re.sub(r"^https?://", "", self.url).split("/")[0].split(":")[0]
            self.session.cookies.set("sid", str(res["sid"]), domain=host, path="/")
        return res

    def logout(self):
        try:
            self._request("GET", "login_web_app.cgi?out")
        except RouterError:
            pass

    def devices(self):
        self.login()
        try:
            data = self._request("GET", "dashboard_device_status_web_app.cgi")
            if data is None:
                last = self.last
                why = (f"redirected to {last['location']} (session not accepted)" if last.get("location")
                       else f"HTTP {last.get('status')}, {last.get('type') or 'no type'}, {last.get('size')} bytes, not JSON, "
                          f"{'; '.join(last.get('json_errors') or []) or 'starts with: ' + repr(last.get('preview'))}")
                cookies = ", ".join(sorted(self.session.cookies.keys())) or "none"
                raise RouterError(f"Signed in, but the router didn't return its device list: {why}. "
                                  f"Cookies from login: {cookies}.")
            # Richer live lists (MAC + IP + status) live on other pages; read them in the same session.
            merged = {"dashboard": data}
            for key, path in self.EXTRA_SOURCES:
                try:
                    extra = self._request("GET", path)
                except RouterError:
                    extra = None
                merged[key] = extra if extra is not None else {"_unavailable": self.last.get("status")}
            data = merged
            devices = parse_devices(data)
            self.layout = layout_summary(data, devices)
            if not devices:
                raise RouterError("Read the router's data but found no devices with MAC addresses in it. "
                                  f"Its layout: {describe_shape(data)}")
            return devices
        finally:
            self.logout()


class RouterLink:
    """Polls the router in the background and feeds its names into the inventory."""

    SETTING = "router"

    def __init__(self, store, interval=120):
        import threading
        self.store = store
        self.interval = interval
        self._client = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self.state = {"configured": False, "url": None, "username": None, "kind": None,
                      "status": "off", "error": None, "last_poll": None, "devices": [],
                      "remembered": False, "suggested_url": None}
        saved = store.get_setting(self.SETTING)
        if saved:
            self._set_client(saved["url"], saved["username"], saved["password"], remembered=True)
        threading.Thread(target=self._loop, name="router", daemon=True).start()

    def _set_client(self, url, username, password, remembered):
        self._client = NokiaRouter(url, username, password)
        self.state.update(configured=True, url=self._client.url, username=username, kind=NokiaRouter.kind,
                          status="connecting", error=None, remembered=remembered)

    def public_state(self):
        if not self.state["configured"] and not self.state["suggested_url"]:
            gw = default_gateway()
            self.state["suggested_url"] = f"https://{gw}" if gw else None
        return dict(self.state)

    def connect(self, url, username, password, remember):
        """Try the credentials now; only keep them if the router accepts them."""
        candidate = NokiaRouter(url, username, password)
        devices = candidate.devices()  # raises RouterError/AuthError
        with self._lock:
            self._set_client(url, username, password, remembered=remember)
            self.store.set_setting(self.SETTING, {"url": candidate.url, "username": username,
                                                  "password": password} if remember else None)
            self._apply(devices, getattr(candidate, "layout", None))
        return self.public_state()

    def disconnect(self):
        with self._lock:
            self._client = None
            self.store.set_setting(self.SETTING, None)
            self.state.update(configured=False, url=None, username=None, kind=None, status="off",
                              error=None, last_poll=None, devices=[], remembered=False)

    def refresh(self):
        self._wake.set()

    def _apply(self, devices, layout=None):
        import time
        from .scanner import is_real_device, vendor_of
        known = {d["mac"]: d for d in self.store.devices()}
        for d in devices:
            if d["active"] and d.get("ip") and is_real_device(d["mac"], d["ip"]):
                self.store.observe(d["mac"], d["ip"], hostname=d.get("name"), vendor=vendor_of(d["mac"]))
            elif d.get("name") and d["mac"] in known:
                self.store.name_from_router(d["mac"], d["name"])
        known = {d["mac"]: d for d in self.store.devices()}
        for d in devices:
            k = known.get(d["mac"])
            d["known"] = bool(k)
            d["trusted"] = bool(k and k["trusted"])
            d["label"] = k and (k["name"] or k["hostname"])
        self.state.update(status="ok", error=None, last_poll=time.time(), devices=devices, layout=layout)

    def _poll(self):
        with self._lock:
            client = self._client
        if client is None:
            return
        try:
            devices = client.devices()
        except RouterError as e:
            with self._lock:
                if self._client is client:
                    self.state.update(status="auth_failed" if isinstance(e, AuthError) else "error", error=str(e))
            return
        with self._lock:
            if self._client is client:
                self._apply(devices, getattr(client, "layout", None))

    def _loop(self):
        while True:
            if self.state["status"] != "auth_failed":  # never hammer a router that rejected us
                self._poll()
            self._wake.wait(self.interval)
            self._wake.clear()
