"""SC-1834: el script de la sonda (embebido en manifests/atlassian-mcp-probe.yaml)
hace el ciclo MCP completo contra un gateway simulado y publica las cuatro métricas.

Hermético: sin clúster ni red externa — un HTTPServer local hace de Keycloak y de
AgentGateway (JSON-RPC sobre POST, con variante SSE y variante isError)."""
import hashlib
import importlib.util
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "manifests" / "atlassian-mcp-probe.yaml"


def load_probe(env):
    cm = next(d for d in yaml.safe_load_all(MANIFEST.read_text())
              if d and d.get("kind") == "ConfigMap")
    import os
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    spec = importlib.util.spec_from_loader("probe_mod", loader=None)
    mod = importlib.util.module_from_spec(spec)
    exec(compile(cm["data"]["probe.py"], "probe.py", "exec"), mod.__dict__)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return mod


class FakeGateway(BaseHTTPRequestHandler):
    """Una escucha para todo: /token (Keycloak) y /mcp (AgentGateway)."""
    mode = "ok"  # ok | sse | iserror | http500

    def do_POST(self):
        path = urlparse(self.path).path
        body = (json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if path != "/token" else {})
        if path == "/token":
            payload = json.dumps({"access_token": "t"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if path != "/mcp" or FakeGateway.mode == "http500":
            self.send_response(500)
            self.end_headers()
            return
        method = body.get("method")
        if method == "initialize":
            self.send_response(200)
            self.send_header("Mcp-Session-Id", "sess-1")
            msg = {"jsonrpc": "2.0", "id": body["id"],
                   "result": {"protocolVersion": "2025-06-18", "capabilities": {},
                              "serverInfo": {"name": "fake", "version": "0"}}}
            if FakeGateway.mode == "sse":
                payload = ("event: message\ndata: " + json.dumps(msg) + "\n\n").encode()
                self.send_header("Content-Type", "text/event-stream")
            else:
                payload = json.dumps(msg).encode()
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif method == "tools/call":
            result = ({"content": [{"type": "text", "text": "issue"}], "isError": True}
                      if FakeGateway.mode == "iserror"
                      else {"content": [{"type": "text", "text": "ok"}], "isError": False})
            payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def log_message(self, *args):
        pass


def serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeGateway)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def run_cycle(mode):
    FakeGateway.mode = mode
    srv, base = serve()
    try:
        mod = load_probe({
            "PROBE_TOKEN_URL": base + "/token",
            "PROBE_MCP_URL": base + "/mcp",
            "PROBE_CLIENT_SECRET": "s",
            "PROBE_ISSUE_KEY": "SC-1",
        })
        mod.cycle()
        return mod
    finally:
        srv.shutdown()


def test_cycle_up_json_and_sse():
    for mode in ("ok", "sse"):
        mod = run_cycle(mode)
        assert mod._state["up"] == 1, mode
        assert mod._state["last_success"] > 0
        assert sum(mod._state["errors"].values()) == 0, mode


def test_cycle_iserror_counts_iserror():
    mod = run_cycle("iserror")
    assert mod._state["up"] == 0
    assert mod._state["errors"]["isError"] == 1


def test_cycle_dead_gateway_counts_http():
    mod = load_probe({
        "PROBE_TOKEN_URL": "http://127.0.0.1:1/token",
        "PROBE_MCP_URL": "http://127.0.0.1:1/mcp",
        "PROBE_CLIENT_SECRET": "s",
        "PROBE_ISSUE_KEY": "SC-1",
    })
    mod.cycle()
    assert mod._state["up"] == 0
    assert mod._state["errors"]["http"] == 1


def test_metrics_endpoint_exposes_the_four_series():
    mod = run_cycle("ok")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        body = urllib.request.urlopen(
            f"http://127.0.0.1:{srv.server_address[1]}/metrics", timeout=5).read().decode()
    finally:
        srv.shutdown()
    for name in ("atlassian_mcp_tool_up", "atlassian_mcp_tool_latency_seconds",
                 "atlassian_mcp_tool_last_success_timestamp_seconds",
                 'atlassian_mcp_probe_errors_total{kind="http"}',
                 'atlassian_mcp_probe_errors_total{kind="timeout"}',
                 'atlassian_mcp_probe_errors_total{kind="isError"}',
                 'atlassian_mcp_probe_errors_total{kind="jsonrpc"}'):
        assert name in body, name


def test_default_mcp_url_points_at_the_real_gateway_service():
    # El Service agentgateway-mcp vive en el namespace `agentgateway` (medido: kubectl get
    # svc -A; no existe el ns `agentgateway-mcp`). Sin env, la sonda debe apuntar ahí: con
    # un ns falso daría up=0 por DNS para siempre y los demás tests no lo verían (inyectan
    # PROBE_MCP_URL).
    for var in ("PROBE_MCP_URL", "PROBE_TOKEN_URL", "PROBE_CLIENT_SECRET", "PROBE_ISSUE_KEY"):
        os.environ.pop(var, None)
    mod = load_probe({})
    assert mod.MCP_URL.startswith(
        "http://agentgateway-mcp.agentgateway.svc.cluster.local:3000/atlassian-probe")


def test_checksum_script_annotation_matches_the_script():
    # El ConfigMap se monta plano: lo único que rueda el pod al editar probe.py es la
    # anotación checksum/script del template. Si alguien edita el script sin refrescarla,
    # este test rompe (patrón checksum/config del gateway).
    docs = list(yaml.safe_load_all(MANIFEST.read_text()))
    cm = next(d for d in docs if d and d.get("kind") == "ConfigMap")
    dep = next(d for d in docs if d and d.get("kind") == "Deployment")
    ann = dep["spec"]["template"]["metadata"]["annotations"]["checksum/script"]
    assert ann == "sha256:" + hashlib.sha256(cm["data"]["probe.py"].encode()).hexdigest()
