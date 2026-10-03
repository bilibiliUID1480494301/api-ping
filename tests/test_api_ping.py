"""Tests for api-ping against a local fake upstream (OpenAI + Anthropic shapes)."""
import contextlib
import http.server
import io
import json
import threading
import unittest

from api_ping.checks import EndpointConfig, chat_ping, list_models, stream_ping
from api_ping.cli import main as cli_main


class FakeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    # ---- helpers -------------------------------------------------------
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        if self.headers.get("Authorization") == "Bearer good":
            return True
        if self.headers.get("x-api-key") == "good":
            return True
        self._json({"error": {"message": "invalid api key"}}, 401)
        return False

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in events:
            self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

    # ---- routes --------------------------------------------------------
    def do_GET(self):
        if not self._authed():
            return
        if self.path == "/v1/models":
            self._json({"object": "list",
                        "data": [{"id": "model-a"}, {"id": "model-b"}]})
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._authed():
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v1/chat/completions":
            if body.get("stream"):
                self._sse([{"choices": [{"delta": {"content": "po"}}]},
                           {"choices": [{"delta": {"content": "ng"}}]}])
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                self._json({"choices": [{"message": {"role": "assistant",
                                                     "content": "pong"}}],
                            "usage": {"total_tokens": 7}})
        elif self.path == "/v1/messages":
            if body.get("stream"):
                self._sse(
                    [{"type": "content_block_delta", "index": 0,
                      "delta": {"type": "text_delta", "text": "po"}},
                     {"type": "content_block_delta", "index": 0,
                      "delta": {"type": "text_delta", "text": "ng"}},
                     {"type": "message_stop"}],
                )
            else:
                self._json({"content": [{"type": "text", "text": "pong"}],
                            "usage": {"input_tokens": 2, "output_tokens": 5}})
        else:
            self.send_error(404)


class FakeUpstreamTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def cfg(self, protocol="openai", key="good"):
        return EndpointConfig(base_url=self.base, api_key=key,
                              protocol=protocol, timeout=5)


class ModelsTests(FakeUpstreamTestCase):
    def test_lists_models(self):
        result = list_models(self.cfg())
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["models"], ["model-a", "model-b"])
        self.assertGreaterEqual(result["latency_ms"], 0)

    def test_bad_key_fails(self):
        result = list_models(self.cfg(key="bad"))
        self.assertFalse(result["ok"])
        self.assertIn("401", result["error"])

    def test_bad_protocol_rejected(self):
        with self.assertRaises(ValueError):
            self.cfg(protocol="grpc")


class ChatTests(FakeUpstreamTestCase):
    def test_openai_chat(self):
        result = chat_ping(self.cfg(), "model-a")
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "pong")
        self.assertEqual(result["total_tokens"], 7)

    def test_anthropic_chat(self):
        result = chat_ping(self.cfg(protocol="anthropic"), "model-a")
        self.assertTrue(result["ok"])
        self.assertEqual(result["reply"], "pong")
        self.assertEqual(result["total_tokens"], 7)

    def test_bad_key_fails(self):
        result = chat_ping(self.cfg(key="nope"), "model-a")
        self.assertFalse(result["ok"])
        self.assertIn("401", result["error"])


class StreamTests(FakeUpstreamTestCase):
    def test_openai_stream(self):
        result = stream_ping(self.cfg(), "model-a")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["chunks"], 2)
        self.assertEqual(result["chars"], 4)
        self.assertIsNotNone(result["first_token_ms"])

    def test_anthropic_stream(self):
        result = stream_ping(self.cfg(protocol="anthropic"), "model-a")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["chars"], 4)
        self.assertGreaterEqual(result["chunks"], 2)

    def test_bad_key_fails(self):
        result = stream_ping(self.cfg(key="nope"), "model-a")
        self.assertFalse(result["ok"])
        self.assertIn("401", result["error"])


class CliTests(FakeUpstreamTestCase):
    def test_json_output_success(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["models", "--base-url", self.base,
                             "--api-key", "good", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["models"]["ok"])

    def test_failure_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli_main(["models", "--base-url", self.base,
                             "--api-key", "bad", "--json"])
        self.assertEqual(code, 1)

    def test_all_subcommand(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli_main(["all", "--base-url", self.base, "--api-key", "good",
                             "--model", "model-a", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(set(payload), {"models", "chat", "stream"})

    def test_missing_key_exits_2(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                cli_main(["models", "--base-url", self.base])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
