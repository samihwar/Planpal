import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from task_parser import OllamaBackend, OpenAIBackend


class TaskParserTemperatureTests(unittest.TestCase):
    def test_openai_parse_uses_zero_temperature(self):
        captured = {}
        openai_module = self._make_openai_module(
            captured,
            '{"title":"Call mom","description":"Call mom","date":null,"time":null,"duration":null}',
        )

        with patch.dict(sys.modules, {"openai": openai_module}):
            parsed = OpenAIBackend(api_key="test-key").parse("Call mom")

        self.assertEqual(parsed["title"], "Call mom")
        self.assertEqual(captured["kwargs"]["temperature"], 0)

    def test_openai_resolve_temporal_update_uses_zero_temperature(self):
        captured = {}
        openai_module = self._make_openai_module(
            captured,
            '{"date":"2026-04-18","time":"09:00"}',
        )

        with patch.dict(sys.modules, {"openai": openai_module}):
            parsed = OpenAIBackend(api_key="test-key").resolve_temporal_update(
                {"title": "Meeting", "description": "Meeting", "date": None, "time": None, "duration": None},
                "tomorrow at 9",
            )

        self.assertEqual(parsed["time"], "09:00")
        self.assertEqual(captured["kwargs"]["temperature"], 0)

    def test_openai_midnight_check_uses_zero_temperature(self):
        captured = {}
        openai_module = self._make_openai_module(captured, '{"keep_midnight_time":true}')

        with patch.dict(sys.modules, {"openai": openai_module}):
            keep_midnight_time = OpenAIBackend(api_key="test-key")._should_keep_midnight_time("midnight")

        self.assertTrue(keep_midnight_time)
        self.assertEqual(captured["kwargs"]["temperature"], 0)

    def test_openai_revision_uses_zero_temperature(self):
        captured = {}
        openai_module = self._make_openai_module(
            captured,
            '{"title":"Call mom","description":"Call mom","date":"2026-04-18","time":null,"duration":null}',
        )

        with patch.dict(sys.modules, {"openai": openai_module}):
            parsed = OpenAIBackend(api_key="test-key").revise_parse(
                "call mom tmrw",
                {"title": "Call mom", "description": "Call mom tmrw", "date": None, "time": None, "duration": None},
            )

        self.assertEqual(parsed["date"], "2026-04-18")
        self.assertEqual(captured["kwargs"]["temperature"], 0)

    def test_ollama_parse_uses_zero_temperature(self):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return self._make_ollama_response(
                '{"title":"Call mom","description":"Call mom","date":null,"time":null,"duration":null}'
            )

        requests_module = self._make_requests_module(fake_post)

        with patch.dict(sys.modules, {"requests": requests_module}):
            parsed = OllamaBackend().parse("Call mom")

        self.assertEqual(parsed["title"], "Call mom")
        self.assertEqual(captured["json"]["options"]["temperature"], 0)

    def test_ollama_resolve_temporal_update_uses_zero_temperature(self):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return self._make_ollama_response('{"date":"2026-04-18","time":"09:00"}')

        requests_module = self._make_requests_module(fake_post)

        with patch.dict(sys.modules, {"requests": requests_module}):
            parsed = OllamaBackend().resolve_temporal_update(
                {"title": "Meeting", "description": "Meeting", "date": None, "time": None, "duration": None},
                "tomorrow at 9",
            )

        self.assertEqual(parsed["time"], "09:00")
        self.assertEqual(captured["json"]["options"]["temperature"], 0)

    def test_ollama_midnight_check_uses_zero_temperature(self):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return self._make_ollama_response('{"keep_midnight_time":true}')

        requests_module = self._make_requests_module(fake_post)

        with patch.dict(sys.modules, {"requests": requests_module}):
            keep_midnight_time = OllamaBackend()._should_keep_midnight_time("midnight")

        self.assertTrue(keep_midnight_time)
        self.assertEqual(captured["json"]["options"]["temperature"], 0)

    def test_ollama_revision_uses_zero_temperature(self):
        captured = {}

        def fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return self._make_ollama_response(
                '{"title":"Call mom","description":"Call mom","date":"2026-04-18","time":null,"duration":null}'
            )

        requests_module = self._make_requests_module(fake_post)

        with patch.dict(sys.modules, {"requests": requests_module}):
            parsed = OllamaBackend().revise_parse(
                "call mom tmrw",
                {"title": "Call mom", "description": "Call mom tmrw", "date": None, "time": None, "duration": None},
            )

        self.assertEqual(parsed["date"], "2026-04-18")
        self.assertEqual(captured["json"]["options"]["temperature"], 0)

    def _make_openai_module(self, captured, response_content):
        class FakeCompletions:
            def create(self, **kwargs):
                captured["kwargs"] = kwargs
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=response_content))]
                )

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAI:
            def __init__(self, api_key):
                captured["api_key"] = api_key
                self.chat = FakeChat()

        module = types.ModuleType("openai")
        module.OpenAI = FakeOpenAI
        return module

    def _make_ollama_response(self, response_content):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"response": response_content},
        )

    def _make_requests_module(self, fake_post):
        module = types.ModuleType("requests")
        module.post = fake_post
        module.Timeout = type("Timeout", (Exception,), {})
        module.ConnectionError = type("ConnectionError", (Exception,), {})
        module.RequestException = Exception
        return module


if __name__ == "__main__":
    unittest.main()
