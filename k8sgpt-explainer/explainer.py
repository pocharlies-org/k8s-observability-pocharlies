#!/usr/bin/env python3
"""Idempotent, event-driven LLM explanations for K8sGPT Results.

K8sGPT's built-in operator integration sends a whole Analyze response through
the LLM and fails the whole analysis when one completion fails.  This worker
keeps the deterministic scanner independent and enriches Result resources one
at a time.  A persistent ConfigMap is the cache and idempotency ledger.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable


LOG = logging.getLogger("k8sgpt-explainer")
UTC = dt.timezone.utc


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def result_namespace(result: dict[str, Any]) -> str:
    name = str((result.get("spec") or {}).get("name") or "")
    return name.split("/", 1)[0] if "/" in name else "_cluster"


def normalized_failures(result: dict[str, Any]) -> list[str]:
    failures = []
    for failure in (result.get("spec") or {}).get("error") or []:
        if isinstance(failure, dict):
            text = failure.get("text", "")
        else:
            text = str(failure)
        normalized = " ".join(str(text).split())
        if normalized:
            failures.append(normalized)
    return sorted(set(failures))


def result_fingerprint(result: dict[str, Any], prompt_version: str) -> str:
    spec = result.get("spec") or {}
    payload = {
        "kind": spec.get("kind") or "unknown",
        "name": spec.get("name") or result.get("metadata", {}).get("name", "unknown"),
        "failures": normalized_failures(result),
        "prompt_version": prompt_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bounded_entries(
    entries: dict[str, dict[str, Any]],
    active_fingerprints: set[str],
    limit: int,
) -> dict[str, dict[str, Any]]:
    if len(entries) <= limit:
        return entries
    protected = {key: value for key, value in entries.items() if key in active_fingerprints}
    remainder = [(key, value) for key, value in entries.items() if key not in protected]
    remainder.sort(key=lambda item: str(item[1].get("last_seen") or ""), reverse=True)
    room = max(0, limit - len(protected))
    protected.update(dict(remainder[:room]))
    return protected


@dataclass(frozen=True)
class Settings:
    namespace: str
    cache_name: str
    allowed_namespaces: frozenset[str]
    model: str
    prompt_version: str
    max_tokens: int
    request_timeout: int
    watch_timeout: int
    max_daily_calls: int
    max_attempts: int
    cache_max_entries: int
    api_key: str
    litellm_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        allowed = {
            item.strip()
            for item in os.environ.get("ALLOWED_NAMESPACES", "").split(",")
            if item.strip()
        }
        api_key = os.environ.get("LITELLM_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("LITELLM_API_KEY is required")
        return cls(
            namespace=os.environ.get("RESULT_NAMESPACE", "k8sgpt"),
            cache_name=os.environ.get("CACHE_CONFIGMAP", "k8sgpt-explanation-cache"),
            allowed_namespaces=frozenset(allowed),
            model=os.environ.get("LITELLM_MODEL", "agent"),
            prompt_version=os.environ.get("PROMPT_VERSION", "v1"),
            max_tokens=int(os.environ.get("MAX_TOKENS", "1024")),
            request_timeout=int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "180")),
            watch_timeout=int(os.environ.get("WATCH_TIMEOUT_SECONDS", "600")),
            max_daily_calls=int(os.environ.get("MAX_DAILY_CALLS", "24")),
            max_attempts=int(os.environ.get("MAX_ATTEMPTS", "2")),
            cache_max_entries=int(os.environ.get("CACHE_MAX_ENTRIES", "256")),
            api_key=api_key,
            litellm_url=os.environ.get(
                "LITELLM_URL",
                "http://litellm.litellm.svc.cluster.local:4000/v1/chat/completions",
            ),
        )


class KubernetesClient:
    def __init__(self, namespace: str) -> None:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST is required")
        self.base_url = f"https://{host}:{port}"
        self.namespace = namespace
        self.token = self._read("/var/run/secrets/kubernetes.io/serviceaccount/token")
        self.context = ssl.create_default_context(
            cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        )

    @staticmethod
    def _read(path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.token}"}
        if payload is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=timeout, context=self.context) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}

    def results_path(self) -> str:
        ns = urllib.parse.quote(self.namespace, safe="")
        return f"/apis/core.k8sgpt.ai/v1alpha1/namespaces/{ns}/results"

    def list_results(self) -> dict[str, Any]:
        return self.request("GET", self.results_path())

    def watch_results(self, resource_version: str, timeout: int) -> Iterable[dict[str, Any]]:
        query = urllib.parse.urlencode(
            {
                "watch": "true",
                "allowWatchBookmarks": "true",
                "resourceVersion": resource_version,
                "timeoutSeconds": str(timeout),
            }
        )
        req = urllib.request.Request(
            f"{self.base_url}{self.results_path()}?{query}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with urllib.request.urlopen(req, timeout=timeout + 30, context=self.context) as response:
            for line in response:
                if line.strip():
                    yield json.loads(line)

    def patch_result(self, name: str, payload: dict[str, Any]) -> None:
        encoded = urllib.parse.quote(name, safe="")
        self.request(
            "PATCH",
            f"{self.results_path()}/{encoded}",
            payload,
            content_type="application/merge-patch+json",
        )

    def configmap_path(self, name: str) -> str:
        ns = urllib.parse.quote(self.namespace, safe="")
        encoded = urllib.parse.quote(name, safe="")
        return f"/api/v1/namespaces/{ns}/configmaps/{encoded}"

    def get_configmap(self, name: str) -> dict[str, Any] | None:
        try:
            return self.request("GET", self.configmap_path(name))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def create_configmap(self, name: str, state: dict[str, Any]) -> None:
        ns = urllib.parse.quote(self.namespace, safe="")
        self.request(
            "POST",
            f"/api/v1/namespaces/{ns}/configmaps",
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": name,
                    "namespace": self.namespace,
                    "labels": {
                        "app.kubernetes.io/name": "k8sgpt-explainer",
                        "app.kubernetes.io/component": "cache",
                    },
                },
                "data": {"state.json": json.dumps(state, separators=(",", ":"))},
            },
        )

    def patch_configmap(self, name: str, state: dict[str, Any]) -> None:
        self.request(
            "PATCH",
            self.configmap_path(name),
            {"data": {"state.json": json.dumps(state, ensure_ascii=False, separators=(",", ":"))}},
            content_type="application/merge-patch+json",
        )


class StateStore:
    def __init__(self, kube: KubernetesClient, settings: Settings) -> None:
        self.kube = kube
        self.settings = settings
        self.state: dict[str, Any] = {}
        self.was_initialized = False

    @staticmethod
    def empty_state() -> dict[str, Any]:
        return {"version": 1, "initialized_at": None, "entries": {}, "budget": {}}

    def load(self) -> None:
        configmap = self.kube.get_configmap(self.settings.cache_name)
        if configmap is None:
            self.state = self.empty_state()
            self.kube.create_configmap(self.settings.cache_name, self.state)
            self.was_initialized = False
            return
        raw = (configmap.get("data") or {}).get("state.json", "")
        try:
            self.state = json.loads(raw) if raw else self.empty_state()
        except json.JSONDecodeError:
            LOG.error("cache state is invalid JSON; refusing to discard idempotency ledger")
            raise
        self.state.setdefault("entries", {})
        self.state.setdefault("budget", {})
        self.was_initialized = bool(self.state.get("initialized_at"))

    def save(self, active_fingerprints: set[str] | None = None) -> None:
        if active_fingerprints is not None:
            self.state["entries"] = bounded_entries(
                self.state["entries"], active_fingerprints, self.settings.cache_max_entries
            )
        self.kube.patch_configmap(self.settings.cache_name, self.state)

    def budget(self, now: dt.datetime) -> dict[str, Any]:
        today = now.date().isoformat()
        budget = self.state.setdefault("budget", {})
        if budget.get("date") != today:
            budget.clear()
            budget.update({"date": today, "calls": 0})
        return budget


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def explain(self, result: dict[str, Any]) -> str:
        spec = result.get("spec") or {}
        failures = normalized_failures(result)
        prompt = (
            "Recurso Kubernetes: "
            f"{spec.get('kind', 'unknown')} {spec.get('name', 'unknown')}\n"
            "Hallazgos deterministas:\n- "
            + "\n- ".join(failures)
        )
        payload = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres SRE de Kubernetes. Explica en español la causa probable, "
                        "las comprobaciones concretas y el arreglo seguro. Sé conciso, "
                        "no inventes estado que no aparece en el hallazgo y no propongas "
                        "borrar recursos como primera medida."
                    ),
                },
                {"role": "user", "content": prompt[:12000]},
            ],
            "max_tokens": self.settings.max_tokens,
            "temperature": 0.1,
            "user": "k8sgpt-explainer",
        }
        req = urllib.request.Request(
            self.settings.litellm_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.settings.request_timeout) as response:
                data = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"LiteLLM HTTP {exc.code}: {body}") from exc
        choices = data.get("choices") or []
        content = choices[0].get("message", {}).get("content") if choices else None
        if not content or not str(content).strip():
            raise RuntimeError("LiteLLM returned an empty explanation")
        return str(content).strip()[:12000]


class Explainer:
    annotation_prefix = "aiops.e-dani.com"

    def __init__(
        self,
        kube: KubernetesClient,
        store: StateStore,
        llm: LiteLLMClient,
        settings: Settings,
    ) -> None:
        self.kube = kube
        self.store = store
        self.llm = llm
        self.settings = settings

    def in_scope(self, result: dict[str, Any]) -> bool:
        return result_namespace(result) in self.settings.allowed_namespaces

    def patch_success(self, result: dict[str, Any], fingerprint: str, explanation: str) -> None:
        name = result["metadata"]["name"]
        self.kube.patch_result(
            name,
            {
                "metadata": {
                    "annotations": {
                        f"{self.annotation_prefix}/explanation-fingerprint": fingerprint,
                        f"{self.annotation_prefix}/explanation-status": "cached",
                        f"{self.annotation_prefix}/explanation-model": self.settings.model,
                        f"{self.annotation_prefix}/prompt-version": self.settings.prompt_version,
                    }
                },
                "spec": {"details": explanation},
            },
        )

    def patch_failure(self, result: dict[str, Any], fingerprint: str, attempts: int) -> None:
        self.kube.patch_result(
            result["metadata"]["name"],
            {
                "metadata": {
                    "annotations": {
                        f"{self.annotation_prefix}/explanation-fingerprint": fingerprint,
                        f"{self.annotation_prefix}/explanation-status": "failed",
                        f"{self.annotation_prefix}/explanation-attempts": str(attempts),
                    }
                }
            },
        )

    def bootstrap(self, results: list[dict[str, Any]], now: dt.datetime) -> None:
        entries = self.store.state["entries"]
        active: set[str] = set()
        first_bootstrap = not self.store.was_initialized
        pending: list[dict[str, Any]] = []
        for result in results:
            if not self.in_scope(result):
                continue
            fingerprint = result_fingerprint(result, self.settings.prompt_version)
            active.add(fingerprint)
            entry = entries.get(fingerprint)
            if entry is not None:
                entry["last_seen"] = isoformat(now)
                continue
            details = str((result.get("spec") or {}).get("details") or "").strip()
            entries[fingerprint] = {
                "status": "success" if details else "seen",
                "explanation": details,
                "attempts": 0,
                "result_name": result.get("metadata", {}).get("name"),
                "source_namespace": result_namespace(result),
                "last_seen": isoformat(now),
            }
            if not first_bootstrap and not details:
                pending.append(result)
        if first_bootstrap:
            self.store.state["initialized_at"] = isoformat(now)
            self.store.was_initialized = True
        self.store.save(active)
        LOG.info(
            "bootstrap complete existing=%d pending_after_restart=%d first_bootstrap=%s",
            len(active),
            len(pending),
            first_bootstrap,
        )
        for result in pending:
            # A Result missed while the watcher was down is still new relative to
            # the persistent ledger. Remove the bootstrap marker so process() can
            # enrich it once.
            fingerprint = result_fingerprint(result, self.settings.prompt_version)
            entries.pop(fingerprint, None)
            self.process(result, now)

    def process(self, result: dict[str, Any], now: dt.datetime | None = None) -> str:
        now = now or utcnow()
        if not self.in_scope(result):
            return "out_of_scope"
        fingerprint = result_fingerprint(result, self.settings.prompt_version)
        entries = self.store.state["entries"]
        entry = entries.get(fingerprint)
        details = str((result.get("spec") or {}).get("details") or "").strip()

        if entry and entry.get("status") == "success":
            explanation = str(entry.get("explanation") or "")
            if explanation and details != explanation:
                self.patch_success(result, fingerprint, explanation)
                LOG.info("cache restore result=%s fingerprint=%s", result["metadata"]["name"], fingerprint[:12])
                return "restored"
            return "cached"
        if entry and entry.get("status") == "seen":
            return "already_seen"
        if entry and entry.get("status") == "failed":
            attempts = int(entry.get("attempts") or 0)
            if attempts >= self.settings.max_attempts:
                return "failed_final"
            next_retry = parse_time(entry.get("next_retry_at"))
            if next_retry and now < next_retry:
                return "retry_wait"

        budget = self.store.budget(now)
        if int(budget.get("calls") or 0) >= self.settings.max_daily_calls:
            entries[fingerprint] = {
                **(entry or {}),
                "status": "deferred",
                "result_name": result["metadata"]["name"],
                "source_namespace": result_namespace(result),
                "last_seen": isoformat(now),
                "next_retry_at": isoformat(
                    (now + dt.timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
                ),
            }
            self.store.save()
            LOG.warning("daily budget exhausted; deferred result=%s", result["metadata"]["name"])
            return "budget_deferred"

        attempts = int((entry or {}).get("attempts") or 0) + 1
        # Count an attempted generation, not only successful ones: failures also
        # consume backend capacity and belong inside the budget.
        budget["calls"] = int(budget.get("calls") or 0) + 1
        self.store.save()
        try:
            explanation = self.llm.explain(result)
        except Exception as exc:
            retry_delay = dt.timedelta(minutes=15 if attempts == 1 else 60)
            entries[fingerprint] = {
                "status": "failed",
                "attempts": attempts,
                "result_name": result["metadata"]["name"],
                "source_namespace": result_namespace(result),
                "last_seen": isoformat(now),
                "next_retry_at": isoformat(now + retry_delay),
                "last_error": str(exc)[:500],
            }
            self.store.save()
            try:
                self.patch_failure(result, fingerprint, attempts)
            except Exception:
                LOG.exception("failed to annotate per-result explanation failure")
            LOG.error(
                "explanation failed result=%s fingerprint=%s attempt=%d error=%s",
                result["metadata"]["name"],
                fingerprint[:12],
                attempts,
                exc,
            )
            return "failed"

        entries[fingerprint] = {
            "status": "success",
            "explanation": explanation,
            "attempts": attempts,
            "result_name": result["metadata"]["name"],
            "source_namespace": result_namespace(result),
            "last_seen": isoformat(now),
            "explained_at": isoformat(now),
        }
        self.store.save()
        self.patch_success(result, fingerprint, explanation)
        LOG.info(
            "explained result=%s fingerprint=%s attempt=%d chars=%d",
            result["metadata"]["name"],
            fingerprint[:12],
            attempts,
            len(explanation),
        )
        return "explained"


def run() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    kube = KubernetesClient(settings.namespace)
    store = StateStore(kube, settings)
    store.load()
    explainer = Explainer(kube, store, LiteLLMClient(settings), settings)

    while True:
        try:
            listing = kube.list_results()
            items = listing.get("items") or []
            resource_version = str((listing.get("metadata") or {}).get("resourceVersion") or "")
            explainer.bootstrap(items, utcnow())
            with open("/tmp/k8sgpt-explainer-ready", "w", encoding="utf-8") as handle:
                handle.write(isoformat(utcnow()))
            for event in kube.watch_results(resource_version, settings.watch_timeout):
                event_type = event.get("type")
                obj = event.get("object") or {}
                metadata = obj.get("metadata") or {}
                if event_type == "BOOKMARK":
                    resource_version = str(metadata.get("resourceVersion") or resource_version)
                    continue
                if event_type in {"ADDED", "MODIFIED"}:
                    explainer.process(obj)
                if metadata.get("resourceVersion"):
                    resource_version = str(metadata["resourceVersion"])
        except urllib.error.HTTPError as exc:
            if exc.code == 410:
                LOG.info("watch resourceVersion expired; relisting")
                continue
            LOG.exception("Kubernetes API error; reconnecting in 10 seconds")
            time.sleep(10)
        except Exception:
            LOG.exception("watch loop failed; reconnecting in 10 seconds")
            time.sleep(10)


if __name__ == "__main__":
    run()
