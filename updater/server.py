"""Update-Dienst für BikeHelper.

Läuft als eigener Container ohne veröffentlichten Port. Nur das Backend erreicht ihn im internen Netz, und nur mit
dem gemeinsamen Token. Er holt per git die neue Version und baut Backend und Frontend neu. Er ändert nichts an der
Datenbank oder an der .env.
"""
import hashlib
import hmac
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT = "/project"
TOKEN = hashlib.sha256(("updater:" + os.environ.get("SECRET_KEY", "")).encode()).hexdigest()
SERVICES = ["backend", "frontend"]  # der Update-Dienst baut sich nicht selbst neu, das macht ./install.sh update

lock = threading.Lock()
job = {"state": "idle", "log": "", "started": None, "error": None, "before": None}


def run(cmd, timeout=1800, log=False):
    p = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    if log:
        job["log"] = (job["log"] + f"$ {' '.join(cmd)}\n{out}\n")[-20000:]
    return p.returncode, out.strip()


def project_name():
    code, out = run(["docker", "inspect", "-f", '{{ index .Config.Labels "com.docker.compose.project" }}', os.environ.get("HOSTNAME", "")], 20)
    return out if code == 0 and out else None


def version():
    code, out = run(["git", "log", "-1", "--format=%h%x09%cs%x09%s"], 20)
    if code != 0:
        return None
    h, d, s = (out.split("\t") + ["", ""])[:3]
    return {"commit": h, "date": d, "subject": s}


def status(check):
    res = {"version": version(), "job": dict(job), "behind": None, "changes": [], "check_error": None, "dirty": False}
    code, out = run(["git", "status", "--porcelain", "--untracked-files=no"], 20)
    res["dirty"] = bool(out)
    if check and job["state"] != "running":
        code, out = run(["git", "fetch", "--quiet"], 60)
        if code != 0:
            res["check_error"] = "Die neue Version konnte nicht abgefragt werden: " + out[-300:]
            return res
        code, out = run(["git", "rev-list", "--count", "HEAD..@{u}"], 20)
        if code != 0:
            res["check_error"] = "Der Ordner folgt keinem Zweig auf GitHub."
            return res
        res["behind"] = int(out or 0)
        if res["behind"]:
            _, log = run(["git", "log", "HEAD..@{u}", "--format=%cs  %s", "-n", "15"], 20)
            res["changes"] = log.splitlines()
    return res


def do_update():
    try:
        name = project_name()
        if not name:
            raise RuntimeError("Der Projektname von Docker Compose wurde nicht gefunden.")
        _, before = run(["git", "rev-parse", "HEAD"], 20)
        job["before"] = before
        code, out = run(["git", "pull", "--ff-only"], 300, log=True)
        if code != 0:
            raise RuntimeError("git pull ist fehlgeschlagen. Lokale Änderungen im Projektordner verhindern das Update oder GitHub ist nicht erreichbar.")
        base = ["docker", "compose", "-p", name, "--project-directory", PROJECT]
        code, out = run(base + ["build", *SERVICES], 3000, log=True)
        if code != 0:
            run(["git", "reset", "--keep", before], 60, log=True)
            raise RuntimeError("Der Bau der neuen Version ist fehlgeschlagen. Die laufende Version bleibt unverändert.")
        job["state"] = "restarting"
        code, out = run(base + ["up", "-d", *SERVICES], 600, log=True)
        if code != 0:
            raise RuntimeError("Der Neustart ist fehlgeschlagen. Schau mit ./install.sh logs nach.")
        job["state"] = "done"
    except Exception as e:  # Fehler für die Oberfläche festhalten
        job["state"], job["error"] = "failed", str(e)
    finally:
        lock.release()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self):
        if hmac.compare_digest(self.headers.get("X-Updater-Token", ""), TOKEN):
            return True
        self._send(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        if not self._auth():
            return
        if self.path.startswith("/status"):
            self._send(200, status("check=1" in self.path))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return
        if self.path != "/update":
            return self._send(404, {"error": "not found"})
        if not lock.acquire(blocking=False):
            return self._send(409, {"error": "Es läuft bereits ein Update."})
        job.update(state="running", log="", error=None, started=None)
        threading.Thread(target=do_update, daemon=True).start()
        self._send(202, {"ok": True})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
