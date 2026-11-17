"""Self-update of a Docker trainer, without commands and without other tools.

Started with access to the Docker engine (``-v /var/run/docker.sock:/var/run/docker.sock``), the trainer fetches the
image of a new version while it is idle and hands over to a short-lived helper container from that image. The helper
replaces the trainer's container by one from the new image with exactly the same settings (name, data volume,
graphics card, restart rule, environment). If the new container does not keep running, the old one is started
again, so a failed update never leaves the trainer off.

Helper: ``python -m trainer.erneuern <old container id> <image>``.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import socket
import sys
import time
from typing import Any
from urllib.parse import quote

_LOG = logging.getLogger("trainer.erneuern")
SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
PRUEFEN_S = 30  # the new container must still run after this long
VERSION_TAG = re.compile(r"\d+\.\d+\.\d+(-gpu)?")


class DockerFehler(RuntimeError):
    pass


class _Verbindung(http.client.HTTPConnection):
    def __init__(self, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)

    def connect(self) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(SOCKET)
        self.sock = s


def _api(art: str, pfad: str, daten: Any = None, timeout: float = 60) -> Any:
    v = _Verbindung(timeout)
    try:
        koerper = json.dumps(daten).encode() if daten is not None else None
        v.request(art, pfad, body=koerper, headers={"Content-Type": "application/json"} if koerper else {})
        r = v.getresponse()
        inhalt = r.read()
    finally:
        v.close()
    if r.status >= 400:
        try:
            meldung = json.loads(inhalt).get("message", "")
        except (ValueError, AttributeError):
            meldung = inhalt[:200].decode(errors="replace")
        raise DockerFehler(f"{art} {pfad.split('?')[0]}: {r.status} {meldung}")
    if not inhalt:
        return {}
    try:
        return json.loads(inhalt)
    except ValueError:
        # streamed answers (image pull): one JSON object per line
        zeilen = [json.loads(z) for z in inhalt.decode(errors="replace").splitlines() if z.strip().startswith("{")]
        fehler = [z["error"] for z in zeilen if z.get("error")]
        if fehler:
            raise DockerFehler(fehler[-1]) from None
        return zeilen


def eigene_id() -> str | None:
    """Id of the container this process runs in (from its mounts, else its host name)."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as datei:
            treffer = re.search(r"/containers/([0-9a-f]{64})/", datei.read())
        if treffer:
            return treffer.group(1)
    except OSError:
        pass
    return socket.gethostname() or None


_verfuegbar: bool | None = None


def verfuegbar() -> bool:
    """True if this trainer runs in Docker with access to the engine and can update itself."""
    global _verfuegbar  # noqa: PLW0603
    if _verfuegbar is None:
        _verfuegbar = False
        if os.path.exists(SOCKET) and (kennung := eigene_id()):
            try:
                _verfuegbar = bool(_api("GET", f"/containers/{kennung}/json", timeout=10).get("Id"))
            except (OSError, DockerFehler, http.client.HTTPException):
                _verfuegbar = False
    return _verfuegbar


def ziel_bild(bild: str, tag_neu: str) -> tuple[str, str]:
    """Repository and tag to fetch: a moving tag (latest, gpu) stays, a fixed version tag moves to the new version."""
    repo, _, tag = bild.rpartition(":")
    if not repo or "/" in tag:
        repo, tag = bild, "latest"
    if VERSION_TAG.fullmatch(tag):
        tag = tag_neu if tag_neu.endswith("-gpu") == tag.endswith("-gpu") else tag_neu
    return repo, tag


def starten(tag_neu: str) -> str:
    """Fetch the new image and start the helper that swaps the container. Returns what happened:
    "aktuell" (already the newest image) or "gestartet" (the helper takes over in a moment)."""
    kennung = eigene_id()
    alt = _api("GET", f"/containers/{kennung}/json")
    repo, tag = ziel_bild(alt["Config"]["Image"], tag_neu)
    _LOG.info("Self-update: fetching %s:%s", repo, tag)
    _api("POST", f"/images/create?fromImage={quote(repo, safe='')}&tag={quote(tag, safe='')}", timeout=3 * 3600)
    neu = _api("GET", f"/images/{quote(repo + ':' + tag, safe='')}/json")
    if neu["Id"] == alt["Image"]:
        return "aktuell"
    quelle = next((m["Source"] for m in alt.get("Mounts", []) if m.get("Destination") == SOCKET), SOCKET)
    name = alt["Name"].lstrip("/")
    try:  # a helper left over from an earlier attempt
        _api("DELETE", f"/containers/{quote(name + '-update', safe='')}?force=1")
    except DockerFehler:
        pass
    helfer = _api("POST", f"/containers/create?name={quote(name + '-update', safe='')}", {
        "Image": neu["Id"],
        "Cmd": ["python", "-m", "trainer.erneuern", alt["Id"], f"{repo}:{tag}"],
        "Env": [f"DOCKER_SOCKET={SOCKET}"],
        "Labels": {"wake-word-studio": "update"},
        "HostConfig": {"Binds": [f"{quelle}:{SOCKET}"], "AutoRemove": True},
    })
    _api("POST", f"/containers/{helfer['Id']}/start")
    _LOG.info("Self-update: helper started, this container is replaced in a moment")
    return "gestartet"


def _ohne(werte: list[str] | None, aus_bild: list[str] | None) -> list[str]:
    weg = set(aus_bild or [])
    return [w for w in werte or [] if w not in weg]


def neue_einstellungen(alt: dict[str, Any], bild_alt: dict[str, Any], bild: str) -> dict[str, Any]:
    """Settings for the new container: everything the user set on the old one, nothing the old image brought along
    (so the new image's own environment, command and volumes apply)."""
    c = dict(alt["Config"])
    b = (bild_alt or {}).get("Config") or {}
    neu: dict[str, Any] = {
        k: v for k, v in c.items()
        if k in ("User", "Tty", "OpenStdin", "StdinOnce", "AttachStdin", "AttachStdout", "AttachStderr",
                 "ExposedPorts", "StopSignal", "StopTimeout", "Domainname")
    }
    neu["Image"] = bild
    neu["Env"] = _ohne(c.get("Env"), b.get("Env"))
    if c.get("Cmd") and c.get("Cmd") != b.get("Cmd"):
        neu["Cmd"] = c["Cmd"]
    if c.get("Entrypoint") and c.get("Entrypoint") != b.get("Entrypoint"):
        neu["Entrypoint"] = c["Entrypoint"]
    if c.get("WorkingDir") and c.get("WorkingDir") != b.get("WorkingDir"):
        neu["WorkingDir"] = c["WorkingDir"]
    if c.get("Hostname") and not alt["Id"].startswith(c["Hostname"]):
        neu["Hostname"] = c["Hostname"]
    labels = {k: v for k, v in (c.get("Labels") or {}).items() if (b.get("Labels") or {}).get(k) != v}
    if labels:
        neu["Labels"] = labels
    host = dict(alt.get("HostConfig") or {})
    # volumes without a name of their own (the data folder when started without -v): keep the same one
    ziele = {str(x).split(":")[1] for x in host.get("Binds") or [] if ":" in str(x)}
    ziele |= {m.get("Target") for m in host.get("Mounts") or []}
    zusatz = [f"{m['Name']}:{m['Destination']}" for m in alt.get("Mounts", [])
              if m.get("Type") == "volume" and m.get("Name") and m.get("Destination") not in ziele]
    if zusatz:
        host["Binds"] = [*(host.get("Binds") or []), *zusatz]
    neu["HostConfig"] = host
    netze = {n: {"Aliases": [a for a in (v.get("Aliases") or []) if not alt["Id"].startswith(a)] or None}
             for n, v in ((alt.get("NetworkSettings") or {}).get("Networks") or {}).items()
             if n not in ("bridge", "host", "none")}
    if netze:
        neu["NetworkingConfig"] = {"EndpointsConfig": netze}
    return neu


def ersetzen(alt_id: str, bild: str) -> bool:
    """Swap the old container for one from ``bild``. True on success; on failure the old one runs again."""
    alt = _api("GET", f"/containers/{alt_id}/json")
    name = alt["Name"].lstrip("/")
    try:
        bild_alt = _api("GET", f"/images/{alt['Image']}/json")
    except DockerFehler:
        bild_alt = {}
    einstellungen = neue_einstellungen(alt, bild_alt, bild)
    _api("POST", f"/containers/{alt_id}/stop?t=60", timeout=120)
    _api("POST", f"/containers/{alt_id}/rename?name={quote(name + '-alt', safe='')}")
    neu_id = None
    try:
        neu_id = _api("POST", f"/containers/create?name={quote(name, safe='')}", einstellungen)["Id"]
        _api("POST", f"/containers/{neu_id}/start")
        time.sleep(PRUEFEN_S)
        zustand = _api("GET", f"/containers/{neu_id}/json")["State"]
        if not zustand.get("Running") or zustand.get("Restarting"):
            raise DockerFehler(f"new container stopped (exit {zustand.get('ExitCode')})")
    except (OSError, DockerFehler, http.client.HTTPException, KeyError) as err:
        _LOG.error("Self-update failed, starting the old trainer again: %s", err)
        if neu_id:
            try:
                _api("DELETE", f"/containers/{neu_id}?force=1")
            except DockerFehler:
                pass
        _api("POST", f"/containers/{alt_id}/rename?name={quote(name, safe='')}")
        _api("POST", f"/containers/{alt_id}/start")
        return False
    _api("DELETE", f"/containers/{alt_id}")  # its volumes stay (data folder)
    try:  # the old image is not needed any more (the graphics card image is large)
        _api("DELETE", f"/images/{alt['Image']}")
    except DockerFehler:
        pass
    _LOG.info("Self-update done: %s runs %s", name, bild)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m trainer.erneuern <container id> <image>")
    raise SystemExit(0 if ersetzen(sys.argv[1], sys.argv[2]) else 1)


if __name__ == "__main__":
    main()
