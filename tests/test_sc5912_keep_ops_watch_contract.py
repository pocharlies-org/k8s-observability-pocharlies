"""SC-5912: el incidente nuevo de Keep despierta la ronda de ops-watch por el gateway de Synapse.

Pins:

1. El workflow `ops-watch-ronda` se dispara con `events: [created]` (NO `on:`, que Keep 0.52.1 descarta en
   silencio; NO `updated`, que Keep emite por cada alerta que suma al incidente, y Alertmanager reenvía cada minuto).
2. Llama a la conexión `synapse_keep` y su `with:` (git) no lleva cabeceras ni token: solo `{incidente, estado}`.
3. La conexión `synapse_keep` de KEEP_PROVIDERS apunta al Service del gateway dentro del clúster y saca el token de
   `X-Synapse-Keep-Token` de 1Password por el Connect (`key: item` + `property: field`).
4. SC-6598: `ops-watch-ronda-resuelto` escucha `events: [updated]` (la resolución sale como `updated`) y su única action
   solo avisa con el incidente RESUELTO: sin ese `if` cada alerta que suma al incidente sería una ronda por minuto. Mismo
   cuerpo `{incidente, estado}` (sin `tipo`, que el adaptador llevaría al dashboard) y misma conexión.
"""

import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow(wid):
    values = yaml.safe_load((ROOT / "keep" / "values.yaml").read_text())
    return next(w for w in values["backend"]["provision"]["workflows"] if w["id"] == wid)


def provisioning():
    docs = yaml.safe_load_all((ROOT / "manifests" / "keep-secrets.yaml").read_text())
    return next(d for d in docs if d and d["metadata"]["name"] == "keepsvc-provisioning")


class OpsWatchRondaTest(unittest.TestCase):
    def test_trigger_es_incidente_creado(self):
        self.assertEqual(workflow("ops-watch-ronda")["triggers"], [{"type": "incident", "events": ["created"]}])

    def test_with_sin_secreto(self):
        (accion,) = workflow("ops-watch-ronda")["actions"]
        self.assertEqual(accion["provider"]["config"], "{{ providers.synapse_keep }}")
        self.assertEqual(accion["provider"]["with"],
                         {"body": {"incidente": "{{ incident.id }}", "estado": "{{ incident.status }}"}})

    def test_conexion_con_token_del_connect(self):
        es = provisioning()
        # El JSON de KEEP_PROVIDERS es una plantilla de ESO: se sustituye cada {{ .x }} por un valor cualquiera.
        plantilla = re.sub(r"\{\{\s*\.(\w+)\s*\}\}", r"<\1>", es["spec"]["target"]["template"]["data"]["KEEP_PROVIDERS"])
        conexion = json.loads(plantilla)["synapse_keep"]
        self.assertEqual(conexion["type"], "webhook")
        self.assertEqual(conexion["authentication"]["url"],
                         "http://synapse-gateway.synapse.svc.cluster.local:18790/webhooks/keep")
        self.assertEqual(conexion["authentication"]["headers"],
                         [{"key": "X-Synapse-Keep-Token", "value": "<synapse_keep_token>"}])
        (dato,) = [d for d in es["spec"]["data"] if d["secretKey"] == "synapse_keep_token"]
        self.assertEqual(dato["sourceRef"]["storeRef"], {"name": "onepassword-connect", "kind": "ClusterSecretStore"})
        self.assertEqual(dato["remoteRef"], {"key": "synapse-webhook-keep", "property": "token"})


class OpsWatchRondaResueltoTest(unittest.TestCase):
    IF = "'{{ incident.status }}' in ['IncidentStatus.RESOLVED', 'resolved']"

    def test_trigger_es_incidente_actualizado(self):
        self.assertEqual(workflow("ops-watch-ronda-resuelto")["triggers"], [{"type": "incident", "events": ["updated"]}])

    def test_solo_avisa_resuelto(self):
        (accion,) = workflow("ops-watch-ronda-resuelto")["actions"]
        self.assertEqual(accion["if"], self.IF)
        # Lo que hace Keep 0.52.1 (step.py): renderiza el `{{ }}` y evalúa con asteval. El enum renderiza su repr.
        for estado, sale in (("IncidentStatus.RESOLVED", True), ("resolved", True), ("IncidentStatus.FIRING", False),
                             ("IncidentStatus.ACKNOWLEDGED", False), ("IncidentStatus.MERGED", False), ("", False)):
            expr = accion["if"].replace("{{ incident.status }}", estado)
            self.assertIs(eval(expr, {"__builtins__": {}}), sale, estado)

    def test_mismo_cuerpo_y_conexion_que_la_ronda(self):
        (accion,) = workflow("ops-watch-ronda-resuelto")["actions"]
        (ronda,) = workflow("ops-watch-ronda")["actions"]
        self.assertEqual(accion["provider"], ronda["provider"])
        self.assertNotIn("tipo", accion["provider"]["with"]["body"])


if __name__ == "__main__":
    unittest.main()
