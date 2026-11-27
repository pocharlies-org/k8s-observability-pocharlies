"""Contracto del camino fantasma del stale-reaper (INFRA-1627).

Un incident `acknowledged` de Keep NO auto-resuelve aunque todas sus alertas
estén resolved (el acknowledged es estado de persona y el motor
`resolveOn: all_resolved` solo actúa sobre `firing`). Cuando el resolved de
Alertmanager llegó a Keep pero el incident estaba acked (el claim de Aurora
acks al nacer), el incident quedaba abierto PARA SIEMPRE: MON-21004 (SC-6648)
y MON-21241 (SC-6824) se cerraron a mano dos veces, y medido el 27-11 había 9
incidents así colgados.

El reaper cierra hoy ese hueco (keep/maintenance/stale-reaper.yaml, camino 2
del encabezado): incident abierto SIN alertas abiertas, `alert_sources` solo
`prometheus`, ningún fingerprint de sus alertas resolved de la ventana vivo en
AM, y `last_seen` más viejo que GRACE_SECONDS -> `POST /incidents/<id>/status
{"status": "resolved"}`. Sin resolved en la ventana no hay comprobación AM
posible y no se toca (conservador por diseño: "no borrar incidentes vivos").

Estos tests ejecutan el reaper.py REAL extraído del ConfigMap contra un stub
HTTP que hace de Keep y de Alertmanager, y comprueban qué llamadas hace y
cuáles NO. Hermetic: localhost only, sin kubectl ni red exterior.
"""

from pathlib import Path
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import yaml

REPO = Path(__file__).resolve().parents[1]
REAPER_YAML = REPO / "keep" / "maintenance" / "stale-reaper.yaml"

OLD = "2026-11-25T00:00:00"  # más viejo que GRACE_SECONDS para todos los casos


def reaper_script():
    docs = list(yaml.safe_load_all(REAPER_YAML.read_text()))
    cm = next(d for d in docs if d["kind"] == "ConfigMap")
    return cm["data"]["reaper.py"]


class Stub(http.server.BaseHTTPRequestHandler):
    state = {}
    posts = []

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/v2/alerts"):
            self._json(200, self.state["am_alerts"])
        elif self.path.startswith("/incidents?"):
            self._json(200, {"items": self.state["incidents"]})
        elif re.match(r"^/incidents/[\w-]+$", self.path):
            iid = self.path.split("/")[2]
            self._json(200, self.state.get("incident_detail", {}).get(iid, {"id": iid, "status": "resolved"}))
        else:
            self._json(404, {})

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        self.posts.append((self.path, body))
        if self.path == "/alerts/query":
            if "resolved" in body.get("cel", ""):
                items = self.state.get("resolved_alerts", [])
            else:
                items = self.state.get("open_alerts", [])
            self._json(200, {"results": items, "count": len(items)})
        elif self.path.startswith("/alerts/event"):
            self._json(202, {})
        elif self.path.startswith("/incidents"):
            self._json(200, {})
        else:
            self._json(404, {})


def run_reaper(state):
    Stub.state = state
    Stub.posts = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(reaper_script())
        path = f.name
    env = {**os.environ, "KEEP_API_URL": base, "KEEP_API_KEY": "stub-key",
           "ALERTMANAGER_URL": base, "PAUSE_SECONDS": "0", "GRACE_SECONDS": "900"}
    try:
        p = subprocess.run([sys.executable, path], env=env,
                           capture_output=True, text=True, timeout=120)
    finally:
        srv.shutdown()
        srv.server_close()
        os.unlink(path)
    return p


def incident(iid, status="acknowledged", sources=("prometheus",), last_seen=OLD):
    return {"id": iid, "status": status, "alert_sources": list(sources),
            "last_seen_time": last_seen}


def base_state(**over):
    st = {
        # Watchdog siempre vivo: la respuesta vacía de AM es "AM roto", no "todo resuelto"
        "am_alerts": [{"fingerprint": "watchdog-fp"}],
        "incidents": [],
        "open_alerts": [],
        "resolved_alerts": [],
    }
    st.update(over)
    return st


def status_closes(posts):
    return [b for p, b in posts
            if re.match(r"^/incidents/[\w-]+/status$", p) and b.get("status") == "resolved"]


class Fantasma(unittest.TestCase):
    def test_cierra_incident_ack_con_todo_resuelto_y_am_limpio(self):
        """El caso MON-21004: incident ack, alerta resolved en Keep, fingerprint fuera de AM."""
        st = base_state(
            incidents=[incident("i-1")],
            resolved_alerts=[{"fingerprint": "fp-1", "incident": "i-1", "status": "resolved"}],
        )
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        closes = status_closes(Stub.posts)
        self.assertEqual(len(closes), 1, f"esperaba 1 cierre, posts={Stub.posts}")

    def test_no_toca_si_am_tiene_una_alerta_del_incident_viva(self):
        """La comprobación de AM es condición: fingerprint vivo -> incident vivo."""
        st = base_state(
            am_alerts=[{"fingerprint": "watchdog-fp"}, {"fingerprint": "fp-1"}],
            incidents=[incident("i-1")],
            resolved_alerts=[{"fingerprint": "fp-1", "incident": "i-1", "status": "resolved"}],
        )
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(status_closes(Stub.posts), [])

    def test_no_toca_incidents_cuya_fuente_no_es_alertmanager(self):
        """x86 (ops-watch) y argocd tienen su propia fuente de verdad (INFRA-882/SC-5269)."""
        st = base_state(
            incidents=[incident("i-x86", sources=("x86",)), incident("i-argo", sources=("argocd",))],
            resolved_alerts=[{"fingerprint": "fp-x", "incident": "i-x86", "status": "resolved"},
                             {"fingerprint": "fp-a", "incident": "i-argo", "status": "resolved"}],
        )
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(status_closes(Stub.posts), [])

    def test_sin_resolved_en_la_ventana_no_se_toca(self):
        """Sin fingerprints comprobables contra AM no hay decisión posible (conservador)."""
        st = base_state(incidents=[incident("i-1")])
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(status_closes(Stub.posts), [])

    def test_grace_no_cierra_incident_recien_visto(self):
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        st = base_state(
            incidents=[incident("i-1", last_seen=now)],
            resolved_alerts=[{"fingerprint": "fp-1", "incident": "i-1", "status": "resolved"}],
        )
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(status_closes(Stub.posts), [])

    def test_con_alertas_abiertas_manda_el_camino_de_zombis(self):
        """Un incident con alertas abiertas no pasa por el camino fantasma (no cierre directo)."""
        st = base_state(
            incidents=[incident("i-1")],
            open_alerts=[{"fingerprint": "fp-9", "incident": "i-1", "status": "firing",
                          "source": ["prometheus"], "labels": {"alertname": "TargetDown"},
                          "startedAt": "2026-11-25 00:00:00"}],
            incident_detail={"i-1": {"id": "i-1", "status": "resolved"}},
        )
        p = run_reaper(st)
        self.assertEqual(p.returncode, 0, p.stderr)
        replays = [b for pth, b in Stub.posts if pth == "/alerts/event/prometheus"]
        self.assertEqual(len(replays), 1, "el zombi se replayea por el canal de ingesta")
        self.assertEqual(replays[0]["status"], "resolved")


class AMInalcanzable(unittest.TestCase):
    def test_am_vacia_no_resuelve_nada(self):
        """Respuesta vacía de AM == AM roto (Watchdog ausente): sale sin tocar nada."""
        st = base_state(
            am_alerts=[],
            incidents=[incident("i-1")],
            resolved_alerts=[{"fingerprint": "fp-1", "incident": "i-1", "status": "resolved"}],
        )
        p = run_reaper(st)
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual(status_closes(Stub.posts), [])


if __name__ == "__main__":
    unittest.main()
