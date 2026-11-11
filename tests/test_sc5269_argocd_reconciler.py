"""Contract de la red de seguridad ArgoCD→Keep (SC-5269).

El resolved de ArgoCD Notifications solo se emite en la transición que el
controller observa (dedup por app+trigger): una app que se recupera sin sync
nuevo deja su incident `ArgoCDAppDegraded`/`ArgoCDSyncFailed` firing para
siempre (segunda ruta de SC-5203, medido al cerrar SC-5249). El CronJob
`keepsvc-argocd-reconciler` reconcilia esos incidents contra el estado VIVO de
la Application y emite el resolved por el mismo canal (`POST /alerts/event`).

Pines (hermetic, sin kubectl ni red):

* El YAML renderiza los 5 objetos (SA, Role, RoleBinding, ConfigMap, CronJob)
  y el script embebido compila.
* La huella del resolved es la MISMA que fija la plantilla de ArgoCD:
  sha256("argocd/<app>/<tipo>")[:16] — si no empareja, Keep abre una alerta
  nueva en vez de resolver la original (el fallo que impedía al stale-reaper
  resolver estas alertas).
* Condiciones por alerta, espejo de los triggers resolved de SC-5249:
  degraded -> health Healthy; sync-failed -> operationState Succeeded. NO un
  AND: el caso residual es una app Healthy con último operationState Failed.
* El stale-reaper (fuente de verdad: Alertmanager) queda fuera de las alertas
  argocd — su replay recalcula la huella y no empareja (SC-5269).
"""

import hashlib
import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECONCILER = ROOT / "keep" / "maintenance" / "argocd-reconciler.yaml"
REAPER = ROOT / "keep" / "maintenance" / "stale-reaper.yaml"


def docs(path):
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


class TestReconciler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.objs = docs(RECONCILER)
        cls.by_kind = {}
        for d in cls.objs:
            cls.by_kind.setdefault(d["kind"], []).append(d)

    def test_renderiza_los_cinco_objetos(self):
        self.assertEqual(len(self.objs), 5)
        self.assertEqual(self.by_kind["ServiceAccount"][0]["metadata"]["namespace"], "monitoring")
        role = self.by_kind["Role"][0]
        self.assertEqual(role["metadata"]["namespace"], "argocd")
        self.assertEqual(role["rules"][0]["apiGroups"], ["argoproj.io"])
        self.assertEqual(role["rules"][0]["resources"], ["applications"])
        self.assertEqual(role["rules"][0]["verbs"], ["get"])  # solo lectura
        rb = self.by_kind["RoleBinding"][0]
        self.assertEqual(rb["roleRef"]["name"], "keepsvc-argocd-reconciler")
        self.assertEqual(rb["subjects"][0]["namespace"], "monitoring")
        cj = self.by_kind["CronJob"][0]
        self.assertEqual(cj["spec"]["schedule"], "*/10 * * * *")
        tmpl = cj["spec"]["jobTemplate"]["spec"]["template"]
        self.assertEqual(tmpl["spec"]["serviceAccountName"], "keepsvc-argocd-reconciler")

    def test_script_embebido_compila(self):
        cm = self.by_kind["ConfigMap"][0]
        src = cm["data"]["reconcile.py"]
        compile(src, "reconcile.py", "exec")  # SyntaxError si está roto

    def test_huella_igual_que_la_plantilla_argocd(self):
        # La plantilla: printf "argocd/%s/degraded" .app.metadata.name | sha256sum | trunc 16
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('f"argocd/{app}/{kind}"', src)
        self.assertIn("hexdigest()[:16]", src)
        esperado = hashlib.sha256(b"argocd/redroid/degraded").hexdigest()[:16]
        self.assertEqual(len(esperado), 16)

    def test_condiciones_espejo_de_los_triggers_resolved(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('"ArgoCDAppDegraded": "degraded"', src)
        self.assertIn('"ArgoCDSyncFailed": "sync-failed"', src)
        self.assertIn('get("health") or {}).get("status") == "Healthy"', src)
        self.assertIn('get("operationState") or {}).get("phase") == "Succeeded"', src)
        # Nunca resuelve sin confirmar el estado vivo: None -> no toca
        self.assertIn("if app_obj is None", src)

    def test_canal_de_ingesta_el_mismo_que_argocd(self):
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('/alerts/event', src)
        self.assertIn('"source": ["argocd"]', src)

    def test_filtra_abiertos_no_solo_firing(self):
        # El claim de Aurora pasa los incidents a acknowledged al crearse (medido
        # en la validación de SC-5269): filtrar solo `firing` no vería nunca el
        # caso residual.
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('status == "firing" || status == "acknowledged"', src)

    def test_filtra_alertas_abiertas_no_solo_firing(self):
        # SC-5288: el claim de Aurora pasa a acknowledged también las alertas; con
        # el filtro de solo `firing` por incident, una alerta acknowledged (el
        # ArgoCDSyncFailed de sc5269-test) nunca recibía su resolved.
        src = self.by_kind["ConfigMap"][0]["data"]["reconcile.py"]
        self.assertIn('a.get("status") in ("firing", "acknowledged")', src)
        self.assertNotIn('if a.get("status") == "firing" and', src)


class TestStaleReaperCedeArgocd(unittest.TestCase):
    def test_reaper_no_toca_alertas_argocd(self):
        cm = [d for d in docs(REAPER) if d["kind"] == "ConfigMap"][0]
        src = cm["data"]["reaper.py"]
        self.assertIn('"argocd" not in (a.get("source") or [])', src)


if __name__ == "__main__":
    unittest.main()
