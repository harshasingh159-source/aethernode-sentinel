import base64
import unittest
from unittest import mock
from urllib.parse import parse_qs

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from aethernode import router as rt
from aethernode.store import Store

KEY = rsa.generate_private_key(public_exponent=65537, key_size=1024)
# the router sends its PEM squashed onto one line
PUB = "".join(KEY.public_key().public_bytes(
    serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode().splitlines())

STATUS = {
    "device_cfg": [
        {"HostName": "Galaxy-S23", "MACAddress": "0E:11:22:33:44:01", "IPAddress": "192.168.1.64",
         "Active": "1", "InterfaceType": "802.11"},
        {"HostName": "old-tablet", "HostAlias": "Sam's tablet", "MACAddress": "AA:BB:CC:00:00:09",
         "IPAddress": "", "Active": "0", "InterfaceType": "802.11"},
    ],
    "Device_status": [{"HostName": "Beacon 2", "HostAlias": ""}],
}


def decrypt_login(body):
    """What the router does with our login POST."""
    q = {k: v[0] for k, v in parse_qs(body).items()}
    assert q["encrypted"] == "1"
    ck = base64.b64decode(q["ck"].replace("-", "+").replace("_", "/").replace(".", "="))
    key_b64, iv_b64 = KEY.decrypt(ck, rsa_padding.PKCS1v15()).decode().split(" ")
    ct = base64.urlsafe_b64decode(q["ct"] + "=" * (-len(q["ct"]) % 4))
    dec = Cipher(algorithms.AES(base64.b64decode(key_b64)), modes.CBC(base64.b64decode(iv_b64))).decryptor()
    unpad = padding.PKCS7(128).unpadder()
    return unpad.update(dec.update(ct) + dec.finalize()) + unpad.finalize()


class FakeNokia(rt.NokiaRouter):
    def __init__(self, *a, accept_password="s3cret&!", **kw):
        super().__init__(*a, **kw)
        self.accept, self.calls, self.logged_in = accept_password, [], False

    def _request(self, method, path, data=None):
        self.calls.append(path)
        if path == "login_web_app.cgi?nonce":
            return {"nonce": "ab+c/d==", "randomKey": "-405", "pubkey": PUB}
        if path == "login_web_app.cgi":
            form = {k: v[0] for k, v in parse_qs(decrypt_login(data).decode()).items()}
            assert form["userhash"] == "admin" and form["nohash"] == "1" and form["nonce"] == "ab-c_d.."
            if form["response"] != self.accept:
                return {"result": 1, "error_msg": "Wrong password."}
            self.logged_in = True
            return {"result": 0, "sid": "abc", "token": "tok"}
        if path == "dashboard_device_status_web_app.cgi":
            return STATUS if self.logged_in else None
        if path in dict(rt.NokiaRouter.EXTRA_SOURCES).values():
            return {"lanhost": [{"MACAddress": "0E:11:22:33:44:01", "IPAddress": "192.168.1.64", "Active": 1}]}
        if path == "login_web_app.cgi?out":
            self.logged_in = False
            return None
        raise AssertionError(path)


class ParseTests(unittest.TestCase):
    def test_parse_devices(self):
        devs = {d["mac"]: d for d in rt.parse_devices(STATUS)}
        self.assertEqual(set(devs), {"0e:11:22:33:44:01", "aa:bb:cc:00:00:09"})
        self.assertEqual(devs["0e:11:22:33:44:01"]["name"], "Galaxy-S23")
        self.assertTrue(devs["0e:11:22:33:44:01"]["active"])
        self.assertEqual(devs["aa:bb:cc:00:00:09"]["name"], "Sam's tablet")  # alias wins
        self.assertFalse(devs["aa:bb:cc:00:00:09"]["active"])

    def test_pem_rewrap(self):
        self.assertIn("\n", rt._pem(PUB).decode())


class ClientTests(unittest.TestCase):
    def test_login_fetch_logout(self):
        r = FakeNokia("192.168.1.254", "admin", "s3cret&!")
        self.assertEqual(r.url, "https://192.168.1.254")
        self.assertEqual(len(r.devices()), 2)
        self.assertEqual(r.calls[-1], "login_web_app.cgi?out")  # never keeps the admin session

    def test_wrong_password(self):
        with self.assertRaises(rt.AuthError):
            FakeNokia("192.168.1.254", "admin", "nope").devices()


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.store.observe("aa:bb:cc:00:00:09", "192.168.1.70")
        patcher = mock.patch.object(rt, "NokiaRouter", FakeNokia)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.link = rt.RouterLink(self.store, interval=3600)

    def test_connect_names_devices_and_remembers(self):
        state = self.link.connect("192.168.1.254", "admin", "s3cret&!", remember=True)
        self.assertEqual(state["status"], "ok")
        self.assertEqual(self.store.device("0e:11:22:33:44:01")["hostname"], "Galaxy-S23")  # active -> added
        self.assertEqual(self.store.device("aa:bb:cc:00:00:09")["hostname"], "Sam's tablet")  # known -> named
        self.assertEqual(self.store.get_setting("router")["username"], "admin")
        self.assertNotIn("password", state)
        self.link.disconnect()
        self.assertIsNone(self.store.get_setting("router"))

    def test_bad_login_not_saved(self):
        with self.assertRaises(rt.AuthError):
            self.link.connect("192.168.1.254", "admin", "wrong", remember=True)
        self.assertIsNone(self.store.get_setting("router"))
        self.assertFalse(self.link.state["configured"])


if __name__ == "__main__":
    unittest.main()


class JsonTests(unittest.TestCase):
    def test_sloppy_json(self):
        self.assertEqual(rt.parse_json(b'\xef\xbb\xbf{"a": [1, 2,],}\n'), {"a": [1, 2]})
        self.assertIsNone(rt.parse_json(b"<html>login</html>"))
        self.assertIsNone(rt.parse_json(b""))


class SplitLayoutTests(unittest.TestCase):
    """Firmware where live status (device_cfg) has no MACs and history (alias_cfg) does."""

    DATA = {
        "device_cfg": [
            {"_oid": 1, "HostName": "Alex-s-Galaxy-M11", "Active": 1, "InterfaceType": "802.11", "IPAddress": "192.168.1.66"},
            {"_oid": 2, "HostName": "iPhone", "Active": 1},
            {"_oid": 3, "HostName": "OnePlus-7T", "Active": 0},
        ],
        "alias_cfg": [
            {"_oid": 1, "HostName": "Alex-s-Galaxy-M11", "MACAddress": "ae:11:22:33:44:02"},
            {"_oid": 2, "HostName": "iPhone", "MACAddress": "32:11:22:33:44:03"},
            {"_oid": 3, "HostName": "iPhone", "MACAddress": "2a:11:22:33:44:04"},
            {"_oid": 4, "HostName": "OnePlus-7T", "MACAddress": "02:00:00:00:00:07"},
        ],
    }

    def test_live_status_matched_by_unique_name(self):
        devs = {d["mac"]: d for d in rt.parse_devices(self.DATA)}
        alex = devs["ae:11:22:33:44:02"]
        self.assertTrue(alex["active"])
        self.assertEqual((alex["ip"], alex["connection"]), ("192.168.1.66", "802.11"))
        self.assertFalse(devs["02:00:00:00:00:07"]["active"])
        # two devices are called "iPhone": ambiguous, so neither is marked connected
        self.assertFalse(devs["32:11:22:33:44:03"]["active"])
        summary = rt.layout_summary(self.DATA, list(devs.values()))
        self.assertEqual(summary["sections"]["device_cfg"]["with_mac"], 0)
        self.assertEqual(summary["active_devices"], 1)


class PortFilterTests(unittest.TestCase):
    def test_router_ports_are_not_devices(self):
        data = {"lan_ether": [{"MACAddress": "00:1b:2c:3d:4e:41", "Enable": 1, "Status": "Up"}],
                "alias_cfg": [{"HostName": "TV", "MACAddress": "aa:00:00:00:00:01"}]}
        self.assertEqual([d["mac"] for d in rt.parse_devices(data)], ["aa:00:00:00:00:01"])


class PlaceholderNameTests(unittest.TestCase):
    def test_unknown_placeholder_is_not_a_name(self):
        data = {"alias_cfg": [{"HostName": "Unknown_0a:11:22:33:44:05", "MACAddress": "0a:11:22:33:44:05"}]}
        self.assertIsNone(rt.parse_devices(data)[0].get("name"))
