"""Contract for the refusal dashboard (DGX-722, P2 of DGX-391).

Pins the shape of ``dashboards/refusal.json`` — the Grafana dashboard of
negativas over ``LiteLLM_SpendLogs`` — so the four epic questions stay
answerable and the datasource wiring cannot drift before it reaches the
cluster:

* four panels, one per question: total counter, rate time series, request
  table, per-model and per-agent breakdown;
* a templating variable filtering censored vs uncensored (``route``);
* every target reads the Postgres datasource with uid ``litellm-pg`` — the
  same uid the live datasource and ``manifests/grafana-refusal.yaml``
  (ExternalSecret) carry; a new uid would silently orphan the panels;
* every figure panel carries the «sin validar» label while DGX-324 keeps the
  detector open (spec DGX-722, criterio 4) — the label is part of the panel,
  not of a page note;
* the authorship header of the refusal-probe base (PolyForm Noncommercial,
  uso interno) stays in the file.

Hermetic: no kubectl, no network.
"""

from pathlib import Path
import json
import unittest

REPO = Path(__file__).resolve().parents[1]
DASHBOARD = REPO / "dashboards" / "refusal.json"

# Los cuatro títulos, en orden de lectura del dashboard.
TITULOS_ESPERADOS = [
    "Negativas — contador (sin validar)",
    "Tasa de negativas sobre selladas (sin validar)",
    "Peticiones negadas (sin validar)",
    "Desglose por modelo y agente (sin validar)",
]


class RefusalDashboardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = json.loads(DASHBOARD.read_text(encoding="utf-8"))
        cls.panels = cls.d["panels"]

    def test_cuatro_paneles_fijos(self):
        """Los cuatro paneles de las preguntas de la épica, con su título."""
        self.assertEqual([p["title"] for p in self.panels], TITULOS_ESPERADOS)

    def test_variable_censored_route(self):
        """El filtro censored/uncensored es variable de plantilla, no texto SQL fijo."""
        names = [v["name"] for v in self.d["templating"]["list"]]
        self.assertTrue(
            any("censored" in n or "route" in n for n in names),
            f"ninguna variable de templating menciona censored/route: {names}",
        )

    def test_datasource_litellm_pg_en_cada_target(self):
        """Cada target lee el datasource Postgres con uid exacto litellm-pg."""
        for panel in self.panels:
            self.assertEqual(
                panel["datasource"]["uid"], "litellm-pg", panel["title"]
            )
            for target in panel["targets"]:
                self.assertEqual(
                    target["datasource"]["uid"],
                    "litellm-pg",
                    f'{panel["title"]} / target {target.get("refId")}',
                )

    def test_sin_validar_por_panel_de_cifras(self):
        """Ninguna cifra se presenta sin la etiqueta «sin validar» (DGX-324 abierto)."""
        for panel in self.panels:
            self.assertIn(
                "sin validar",
                json.dumps(panel, ensure_ascii=False),
                f'panel sin la etiqueta «sin validar»: {panel["title"]}',
            )

    def test_cabecera_autoria(self):
        """La cabecera declara la base de refusal-probe y su licencia."""
        header = self.d.get("__comment", "")
        self.assertIn("refusal-probe", header)
        self.assertIn("PolyForm", header)


if __name__ == "__main__":
    unittest.main()
