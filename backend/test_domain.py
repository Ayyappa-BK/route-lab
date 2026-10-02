import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import domain


class RoutingTests(unittest.TestCase):
    def setUp(self):
        with domain.LOCK:
            domain.WINDOW.clear()
            domain.BREAKER.update(state="closed", failures=0, opened_at=0, probe=False)
        domain.configure({"failure_rate": 0, "latency_ms": 0})

    def test_outage_opens_and_skips_primary(self):
        domain.configure({"failure_rate": 1, "latency_ms": 0})
        for _ in range(3):
            self.assertTrue(domain.infer("great")["primary_failed"])
        event = domain.infer("great")
        self.assertEqual(event["breaker"], "open")
        self.assertEqual(event["route"], "fallback")
        self.assertFalse(event["primary_failed"])

    def test_probe_closes_after_cooldown(self):
        domain.BREAKER.update(state="open", opened_at=0, failures=3)
        with patch.object(domain, "CLOCK", return_value=4):
            event = domain.infer("bad")
        self.assertEqual(event["route"], "primary")
        self.assertEqual(event["breaker"], "closed")

    def test_only_one_probe(self):
        domain.BREAKER.update(state="open", opened_at=0, failures=3)
        self.assertEqual(domain.choose(4), (True, True))
        self.assertEqual(domain.choose(4), (False, False))
        domain.settle(False, True, 4)
        self.assertEqual(domain.choose(5), (False, False))

    def test_bounded_window_and_concurrency(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(domain.infer, ["great"] * 205))
        state = domain.snapshot()
        self.assertEqual(state["metrics"]["requests"], 200)
        self.assertEqual(len({e["trace"] for e in state["events"]}), 200)

    def test_invalid_configuration_does_not_mutate(self):
        before = dict(domain.CONFIG)
        for rate in [-1, float("nan"), True]:
            with self.assertRaises(ValueError):
                domain.configure({"failure_rate": rate, "latency_ms": 5})
        self.assertEqual(domain.CONFIG, before)

    def test_capacity_limit(self):
        for _ in range(8):
            domain.ADMISSION.acquire()
        try:
            with self.assertRaises(ValueError):
                domain.infer("great")
        finally:
            for _ in range(8):
                domain.ADMISSION.release()
