import json
import unittest
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import Handler


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_health(self):
        with urlopen(self.base + "/api/health", timeout=3) as response:
            self.assertEqual(json.load(response), {"status": "ok"})

    def test_malformed_json(self):
        request = Request(
            self.base + "/api/missing",
            data=b"{",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        self.assertEqual(context.exception.code, 400)
        self.assertIn("error", json.load(context.exception))

    def test_array_body_rejected(self):
        request = Request(
            self.base + "/api/missing",
            data=b"[]",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        self.assertEqual(context.exception.code, 400)

    def test_size_limit(self):
        request = Request(
            self.base + "/api/missing",
            data=b"{}",
            headers={"Content-Length": "2000001"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        self.assertEqual(context.exception.code, 413)

    def test_unknown_api(self):
        with self.assertRaises(HTTPError) as context:
            urlopen(self.base + "/api/missing", timeout=3)
        self.assertEqual(context.exception.code, 404)
