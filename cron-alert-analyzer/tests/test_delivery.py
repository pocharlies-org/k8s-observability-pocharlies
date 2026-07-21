import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import kubernetes.config


os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:unit-test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "-1000000000000")
os.environ.setdefault("TELEGRAM_THREAD_ID", "34494")
os.environ.setdefault("LITELLM_API_KEY", "unit-test-llm-key")
os.environ.setdefault("APP_VERSION", "test")

# Importing the app normally initializes Kubernetes clients. Unit tests do not
# need a cluster, so neutralize only config loading before importing main.
kubernetes.config.load_incluster_config = lambda: None
kubernetes.config.load_kube_config = lambda: None
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.content = b"response"

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.posts = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, _url, data):
        self.posts += 1
        self.last_data = data
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TelegramDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.TELEGRAM_DELIVERY_ATTEMPTS.update(success=0, failure=0)
        main.TELEGRAM_DELIVERY_RETRIES = 0
        main.TELEGRAM_LAST_ATTEMPT_TIMESTAMP = 0.0
        main.TELEGRAM_LAST_SUCCESS_TIMESTAMP = 0.0

    async def test_success_is_recorded_once(self):
        fake = FakeClient([FakeResponse(200, {"ok": True})])
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            self.assertTrue(await main.send_telegram("test"))
        self.assertEqual(fake.posts, 1)
        self.assertEqual(main.TELEGRAM_DELIVERY_ATTEMPTS, {"success": 1, "failure": 0})

    async def test_permanent_400_is_not_retried(self):
        fake = FakeClient([FakeResponse(400, {"ok": False, "description": "message thread not found"})])
        with patch.object(main.httpx, "AsyncClient", return_value=fake):
            self.assertFalse(await main.send_telegram("test"))
        self.assertEqual(fake.posts, 1)
        self.assertEqual(main.TELEGRAM_DELIVERY_ATTEMPTS, {"success": 0, "failure": 1})

    async def test_retryable_5xx_recovers(self):
        fake = FakeClient([
            FakeResponse(500, {"ok": False, "description": "temporary"}),
            FakeResponse(502, {"ok": False, "description": "temporary"}),
            FakeResponse(200, {"ok": True}),
        ])
        sleep = AsyncMock()
        with patch.object(main.httpx, "AsyncClient", return_value=fake), patch.object(main.asyncio, "sleep", sleep):
            self.assertTrue(await main.send_telegram("test"))
        self.assertEqual(fake.posts, 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(main.TELEGRAM_DELIVERY_RETRIES, 2)
        self.assertEqual(main.TELEGRAM_DELIVERY_ATTEMPTS, {"success": 1, "failure": 0})

    async def test_transport_failure_is_retried_and_recorded(self):
        request = httpx.Request("POST", "https://api.telegram.org/redacted")
        fake = FakeClient([
            httpx.ConnectError("connection failed", request=request),
            httpx.ReadTimeout("timed out", request=request),
            httpx.ConnectError("connection failed", request=request),
        ])
        sleep = AsyncMock()
        with patch.object(main.httpx, "AsyncClient", return_value=fake), patch.object(main.asyncio, "sleep", sleep):
            self.assertFalse(await main.send_telegram("test"))
        self.assertEqual(fake.posts, 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(main.TELEGRAM_DELIVERY_RETRIES, 2)
        self.assertEqual(main.TELEGRAM_DELIVERY_ATTEMPTS, {"success": 0, "failure": 1})

    def test_sensitive_filter_redacts_both_credentials(self):
        import logging

        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "%s %s",
            (main.TELEGRAM_BOT_TOKEN, main.LITELLM_API_KEY),
            None,
        )
        self.assertTrue(main._SensitiveValueFilter().filter(record))
        rendered = record.getMessage()
        self.assertNotIn(main.TELEGRAM_BOT_TOKEN, rendered)
        self.assertNotIn(main.LITELLM_API_KEY, rendered)
        self.assertEqual(rendered, "[REDACTED] [REDACTED]")

    def test_metrics_exposes_delivery_and_build_series(self):
        body = main.metrics()
        self.assertIn("cron_alert_analyzer_build_info", body)
        self.assertIn("cron_alert_analyzer_telegram_delivery_attempts_total", body)
        self.assertIn("cron_alert_analyzer_telegram_delivery_retries_total", body)
        self.assertIn("cron_alert_analyzer_telegram_delivery_last_success_timestamp_seconds", body)


if __name__ == "__main__":
    unittest.main()
