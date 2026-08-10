import datetime as dt
import importlib.util
import pathlib
import sys
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "explainer.py"
SPEC = importlib.util.spec_from_file_location("explainer", MODULE_PATH)
explainer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = explainer
SPEC.loader.exec_module(explainer)


def sample_result(*, error="pod is not ready", details="", name="skirmshop/api"):
    return {
        "metadata": {"name": "skirmshopapi"},
        "spec": {
            "kind": "Pod",
            "name": name,
            "error": [{"text": error}],
            "details": details,
        },
    }


class FakeKube:
    def __init__(self):
        self.patches = []

    def patch_result(self, name, payload):
        self.patches.append((name, payload))


class FakeStore:
    def __init__(self, initialized=True):
        self.state = {"version": 1, "initialized_at": "now" if initialized else None, "entries": {}, "budget": {}}
        self.was_initialized = initialized
        self.saved = 0

    def save(self, active_fingerprints=None):
        self.saved += 1

    def budget(self, now):
        today = now.date().isoformat()
        if self.state["budget"].get("date") != today:
            self.state["budget"] = {"date": today, "calls": 0}
        return self.state["budget"]


class FakeLLM:
    def __init__(self, response="explicación"):
        self.calls = 0
        self.response = response

    def explain(self, result):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def settings(**overrides):
    base = dict(
        namespace="k8sgpt",
        cache_name="cache",
        allowed_namespaces=frozenset({"skirmshop", "_cluster"}),
        model="agent",
        prompt_version="v1",
        max_tokens=1024,
        request_timeout=180,
        watch_timeout=600,
        max_daily_calls=24,
        max_attempts=2,
        cache_max_entries=256,
        api_key="test",
        litellm_url="http://example.invalid",
    )
    base.update(overrides)
    return explainer.Settings(**base)


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_ignores_details_and_error_order(self):
        left = sample_result(details="old")
        left["spec"]["error"].append({"text": "  second   error "})
        right = sample_result(details="new")
        right["spec"]["error"] = [{"text": "second error"}, {"text": "pod is not ready"}]
        self.assertEqual(
            explainer.result_fingerprint(left, "v1"),
            explainer.result_fingerprint(right, "v1"),
        )

    def test_namespace_extraction(self):
        self.assertEqual(explainer.result_namespace(sample_result()), "skirmshop")
        self.assertEqual(explainer.result_namespace(sample_result(name="node-1")), "_cluster")


class IdempotencyTests(unittest.TestCase):
    NOW = dt.datetime(2026, 8, 10, 20, 0, tzinfo=dt.timezone.utc)

    def make_worker(self, *, initialized=True, llm_response="explicación", **setting_overrides):
        kube = FakeKube()
        store = FakeStore(initialized=initialized)
        llm = FakeLLM(llm_response)
        worker = explainer.Explainer(kube, store, llm, settings(**setting_overrides))
        return worker, kube, store, llm

    def test_first_bootstrap_marks_existing_without_calling_llm(self):
        worker, _, store, llm = self.make_worker(initialized=False)
        result = sample_result()
        worker.bootstrap([result], self.NOW)
        fingerprint = explainer.result_fingerprint(result, "v1")
        self.assertEqual(store.state["entries"][fingerprint]["status"], "seen")
        self.assertEqual(llm.calls, 0)
        self.assertEqual(worker.process(result, self.NOW), "already_seen")
        self.assertEqual(llm.calls, 0)

    def test_new_fingerprint_is_explained_once_then_restored_from_cache(self):
        worker, kube, _, llm = self.make_worker()
        result = sample_result(error="brand new failure")
        self.assertEqual(worker.process(result, self.NOW), "explained")
        self.assertEqual(llm.calls, 1)
        self.assertEqual(worker.process(result, self.NOW), "restored")
        self.assertEqual(llm.calls, 1)
        self.assertEqual(len(kube.patches), 2)

    def test_one_failure_is_local_and_retries_only_that_fingerprint(self):
        worker, _, store, llm = self.make_worker(llm_response=RuntimeError("backend down"))
        failed = sample_result(error="failure A")
        self.assertEqual(worker.process(failed, self.NOW), "failed")
        self.assertEqual(worker.process(failed, self.NOW + dt.timedelta(minutes=1)), "retry_wait")
        self.assertEqual(llm.calls, 1)
        llm.response = "second result works"
        other = sample_result(error="failure B")
        self.assertEqual(worker.process(other, self.NOW + dt.timedelta(minutes=1)), "explained")
        self.assertEqual(llm.calls, 2)
        self.assertEqual(store.state["budget"]["calls"], 2)

    def test_daily_budget_defers_without_call(self):
        worker, _, store, llm = self.make_worker(max_daily_calls=1)
        store.state["budget"] = {"date": self.NOW.date().isoformat(), "calls": 1}
        self.assertEqual(worker.process(sample_result(error="new"), self.NOW), "budget_deferred")
        self.assertEqual(llm.calls, 0)


if __name__ == "__main__":
    unittest.main()
