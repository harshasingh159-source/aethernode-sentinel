"""System-tray front end for the Windows app: no console window, an icon by the clock,
a small menu, and a Windows notification whenever a new device joins."""
import logging
import os
import subprocess
import threading
import time
import webbrowser

log = logging.getLogger("aethernode.tray")

GREEN = (52, 211, 153, 255)
AMBER = (245, 158, 11, 255)
BG = (11, 15, 20, 255)


def draw_icon(size=64, alert=False):
    """The radar logo; amber when untrusted devices are online."""
    from PIL import Image, ImageDraw
    color = AMBER if alert else GREEN
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=BG)
    m = size * 0.16
    d.ellipse([m, m, size - m, size - m], outline=color, width=max(2, size // 14))
    c = size * 0.36
    d.ellipse([c, c, size - c, size - c], fill=color)
    return img


class Tray:
    def __init__(self, url, store, data_dir, on_quit, scanner=None):
        import pystray
        self.url, self.store, self.data_dir, self.on_quit = url, store, data_dir, on_quit
        self.scanner = scanner
        self._alert = None
        self._primed = False  # no alerts until the first scan is done (it "discovers" everything)
        self._last_event_id = self._newest_event_id()
        self.icon = pystray.Icon(
            "AetherNode", draw_icon(), "AetherNode",
            menu=pystray.Menu(
                pystray.MenuItem("Open dashboard", self.open_dashboard, default=True),
                pystray.MenuItem(lambda _: self._status_text(), None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open data folder", self.open_folder),
                pystray.MenuItem("Quit AetherNode", self.quit),
            ),
        )

    # ---- menu actions
    def open_dashboard(self, *_):
        webbrowser.open(self.url)

    def open_folder(self, *_):
        if os.name == "nt":
            os.startfile(self.data_dir)  # noqa: S606 - opens Explorer on our own folder
        else:
            subprocess.Popen(["xdg-open", str(self.data_dir)])

    def quit(self, *_):
        self.icon.visible = False
        self.on_quit()
        self.icon.stop()

    # ---- status + notifications
    def _status_text(self):
        try:
            c = self.store.counts()
            return f"{c['online']} online · {c['untrusted']} need review"
        except Exception:
            return "Starting…"

    def _newest_event_id(self):
        try:
            ev = self.store.events(limit=1)
            return ev[0]["id"] if ev else 0
        except Exception:
            return 0

    def _watch(self):
        while True:
            time.sleep(5)
            try:
                c = self.store.counts()
                alert = c["untrusted_online"] > 0
                self.icon.title = (f"AetherNode: {c['online']} online, {c['untrusted_online']} untrusted online"
                                   if c["total"] else "AetherNode: scanning…")
                if alert != self._alert:
                    self._alert = alert
                    self.icon.icon = draw_icon(alert=alert)
                if not self._primed:
                    if self.scanner is None or self.scanner.state.get("last_scan"):
                        self._primed = True
                        self._last_event_id = self._newest_event_id()
                    self.icon.update_menu()
                    continue
                new = [e for e in self.store.events(limit=20) if e["id"] > self._last_event_id]
                if new:
                    self._last_event_id = max(e["id"] for e in new)
                    joined = [e for e in reversed(new) if e["kind"] == "joined"]
                    if joined:
                        who = ", ".join((e["label"] or e["detail"] or e["mac"]) for e in joined[:3])
                        more = f" and {len(joined) - 3} more" if len(joined) > 3 else ""
                        self.icon.notify(f"{who}{more}", "New device on your network")
                self.icon.update_menu()
            except Exception:
                log.debug("tray update failed", exc_info=True)

    def run(self):
        """Blocks until Quit (must run on the main thread on Windows)."""
        def setup(icon):
            icon.visible = True
            threading.Thread(target=self._watch, name="tray-watch", daemon=True).start()
            icon.notify("Running in the background. Click this icon to open the dashboard.", "AetherNode")
        self.icon.run(setup=setup)
