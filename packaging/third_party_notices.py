"""Write dist/THIRD_PARTY_NOTICES.txt: every library bundled into AetherNode.exe, with its
version, license and full license text (open-source licenses require shipping these).

It walks the installed dependency tree of the packages the .exe bundles, so run it in the
same environment that builds the .exe (the build script does).
"""
import re
import sys
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOTS = ["fastapi", "uvicorn", "requests", "cryptography", "scapy", "pystray", "pillow"]
ENV = default_environment()
LICENSE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.I)


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def collect():
    seen, todo = {}, list(ROOTS)
    while todo:
        name = norm(todo.pop())
        if name in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[name] = dist
        for spec in dist.requires or []:
            req = Requirement(spec)
            if req.marker and not req.marker.evaluate({**ENV, "extra": ""}):
                continue  # optional extra or other platform
            todo.append(req.name)
    return seen


def license_of(dist):
    md = dist.metadata
    expr = md.get("License-Expression")
    if expr:
        return expr
    classifiers = [c.split(" :: ")[-1] for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    text = (md.get("License") or "").strip()
    short = text if text and "\n" not in text and len(text) < 80 else ""
    return ", ".join(classifiers) or short or "see license text below"


def license_texts(dist):
    out = []
    for f in dist.files or []:
        if LICENSE_FILE.search(str(f)):
            try:
                out.append((str(f), Path(dist.locate_file(f)).read_text(encoding="utf-8", errors="replace")))
            except OSError:
                pass
    if not out and dist.metadata.get("License") and "\n" in dist.metadata.get("License"):
        out.append(("License (from package metadata)", dist.metadata.get("License")))
    return out


def main(out_path):
    dists = collect()
    lines = [
        "AetherNode.exe - third-party notices",
        "=" * 40,
        "",
        "AetherNode itself is MIT licensed (see LICENSE). The Windows .exe also bundles the",
        "components below, each under its own license. Notably, Scapy is GPL-2.0-only and",
        "pystray is LGPL-3.0: if you redistribute the .exe, follow those licenses too. The",
        "complete corresponding source is at https://github.com/harshasingh159-source/aethernode-sentinel",
        "and each component's source is available from its project (see Home-page below).",
        "",
        f"Python {sys.version.split()[0]} - PSF License (https://docs.python.org/3/license.html)",
        "PyInstaller bootloader - GPL-2.0 with a bootloader exception that permits distributing",
        "  bundled applications under any license (https://pyinstaller.org/en/stable/license.html)",
        "",
        "Bundled Python packages",
        "-" * 23,
    ]
    for name in sorted(dists):
        d = dists[name]
        home = d.metadata.get("Home-page") or next(
            (u.split(",", 1)[1].strip() for u in d.metadata.get_all("Project-URL") or []
             if u.lower().startswith(("source", "homepage", "repository", "home"))), "")
        lines.append(f"{d.metadata['Name']} {d.version} - {license_of(d)}" + (f" - {home}" if home else ""))
    lines += ["", "", "Full license texts", "=" * 18]
    for name in sorted(dists):
        d = dists[name]
        for fname, text in license_texts(d):
            lines += ["", "-" * 78, f"{d.metadata['Name']} {d.version}: {fname}", "-" * 78, text.rstrip()]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path}: {len(dists)} packages")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dist/THIRD_PARTY_NOTICES.txt")
