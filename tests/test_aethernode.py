"""Run with:  python -m unittest"""
import unittest

from fastapi.testclient import TestClient

from aethernode.scanner import is_real_device, normalize_mac, parse_neighbour_table
from aethernode.server import create_app
from aethernode.store import Store

WINDOWS_ARP = """
Interface: 192.168.1.65 --- 0x4
  Internet Address      Physical Address      Type
  192.168.1.64          0e-11-22-33-44-01     dynamic
  192.168.1.254         00-1b-2c-3d-4e-40     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
"""
LINUX_PROC = """IP address       HW type     Flags       HW address            Mask     Device
192.168.0.1      0x1         0x2         a4:91:b1:00:11:22     *        wlan0
192.168.0.9      0x1         0x0         00:00:00:00:00:00     *        wlan0
"""
MAC_ARP = """? (10.0.0.1) at 0:1e:c2:a:b:c on en0 ifscope [ethernet]
? (10.0.0.7) at (incomplete) on en0 ifscope [ethernet]"""


class ParsingTests(unittest.TestCase):
    def test_windows(self):
        pairs = parse_neighbour_table(WINDOWS_ARP)
        self.assertIn(("0e:11:22:33:44:01", "192.168.1.64"), pairs)
        real = [p for p in pairs if is_real_device(*p)]
        self.assertEqual(len(real), 2)  # broadcast + multicast dropped

    def test_linux_proc(self):
        real = [p for p in parse_neighbour_table(LINUX_PROC) if is_real_device(*p)]
        self.assertEqual(real, [("a4:91:b1:00:11:22", "192.168.0.1")])

    def test_macos_short_octets(self):
        self.assertEqual(parse_neighbour_table(MAC_ARP), [("00:1e:c2:0a:0b:0c", "10.0.0.1")])

    def test_normalize(self):
        self.assertEqual(normalize_mac("AA-BB-CC-0-1-2"), "aa:bb:cc:00:01:02")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.s = Store(":memory:")
        self.addCleanup(self.s.close)

    def kinds(self):
        return [e["kind"] for e in reversed(self.s.events())]

    def test_lifecycle(self):
        self.assertEqual(self.s.observe("aa:00:00:00:00:01", "10.0.0.5", now=100), "joined")
        self.assertIsNone(self.s.observe("aa:00:00:00:00:01", "10.0.0.5", now=160))
        self.assertEqual(self.s.expire(older_than=200, now=300), 1)
        self.assertFalse(self.s.device("aa:00:00:00:00:01")["online"])
        self.assertEqual(self.s.observe("aa:00:00:00:00:01", "10.0.0.6", now=400), "online")
        self.assertEqual(self.kinds(), ["joined", "offline", "ip_changed", "online"])

    def test_self_is_trusted_and_private_mac_flagged(self):
        self.s.observe("00:1a:2b:3c:4d:5e", "10.0.0.2", is_self=True)
        self.s.observe("0e:11:22:33:44:01", "10.0.0.3")
        me, phone = self.s.device("00:1a:2b:3c:4d:5e"), self.s.device("0e:11:22:33:44:01")
        self.assertTrue(me["trusted"] and me["is_self"] and not me["private_mac"])
        self.assertTrue(phone["private_mac"] and not phone["trusted"])
        self.assertEqual(self.s.counts()["untrusted"], 1)

    def test_self_trusted_even_if_seen_first_by_live_engine(self):
        self.s.observe("00:1a:2b:3c:4d:5e", "10.0.0.2")
        self.s.observe("00:1a:2b:3c:4d:5e", "10.0.0.2", is_self=True)
        self.assertTrue(self.s.device("00:1a:2b:3c:4d:5e")["trusted"])

    def test_hostname_not_overwritten_by_none(self):
        self.s.observe("aa:00:00:00:00:01", "10.0.0.5", hostname="tv.lan")
        self.s.observe("aa:00:00:00:00:01", "10.0.0.5")
        self.assertEqual(self.s.device("aa:00:00:00:00:01")["hostname"], "tv.lan")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.store.observe("aa:00:00:00:00:01", "10.0.0.5")
        self.c = TestClient(create_app(self.store))

    def test_flow(self):
        self.assertEqual(self.c.get("/api/status").json()["counts"]["untrusted"], 1)
        r = self.c.patch("/api/devices/AA-00-00-00-00-01", json={"name": " TV ", "trusted": True})
        self.assertEqual((r.json()["name"], r.json()["trusted"]), ("TV", True))
        self.assertEqual(self.c.get("/api/status").json()["counts"]["trusted"], 1)
        self.assertEqual(self.c.get("/api/events").json()[0]["kind"], "trusted")
        self.assertEqual(self.c.delete("/api/devices/aa:00:00:00:00:01").status_code, 200)
        self.assertEqual(self.c.get("/api/devices").json(), [])

    def test_errors(self):
        self.assertEqual(self.c.patch("/api/devices/ff:ff:ff:ff:ff:fe", json={"trusted": True}).status_code, 404)
        self.assertEqual(self.c.patch("/api/devices/aa:00:00:00:00:01", json={"name": "x" * 65}).status_code, 422)
        self.assertEqual(self.c.post("/api/scan").status_code, 503)  # no scanner attached

    def test_dashboard_served(self):
        r = self.c.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("AetherNode", r.text)


if __name__ == "__main__":
    unittest.main()
