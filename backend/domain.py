import math
import random
import re
import threading
import time
import uuid
from collections import deque

LOCK = threading.RLock()
WINDOW = deque(maxlen=200)
CLOCK = time.monotonic
CONFIG = {"failure_rate": 0.0, "latency_ms": 35, "cooldown_seconds": 3}
BREAKER = {"state": "closed", "failures": 0, "opened_at": 0.0, "probe": False}
RNG = random.Random(41)
ADMISSION = threading.BoundedSemaphore(8)


class ProviderFailure(Exception):
    pass


def provider(text, primary, failure, latency):
    time.sleep(latency / 1000 if primary else 0.008)
    if primary and failure:
        raise ProviderFailure("Primary provider unavailable")
    words = set(re.findall(r"[a-z]+", text.lower()))
    positive = len(words & {"good", "great", "love", "fast", "excellent"})
    negative = len(words & {"bad", "slow", "hate", "broken", "awful"})
    return {
        "label": "positive"
        if positive > negative
        else "negative"
        if negative > positive
        else "neutral",
        "model": "lexicon-v1",
    }


def choose(now):
    with LOCK:
        if BREAKER["state"] == "open":
            if now - BREAKER["opened_at"] < CONFIG["cooldown_seconds"]:
                return False, False
            BREAKER["state"] = "half-open"
        if BREAKER["state"] == "half-open":
            if BREAKER["probe"]:
                return False, False
            BREAKER["probe"] = True
            return True, True
        return True, False


def settle(success, probe, now):
    with LOCK:
        if probe:
            BREAKER.update(
                state="closed" if success else "open",
                failures=0 if success else 3,
                opened_at=now,
                probe=False,
            )
        elif BREAKER["state"] == "closed":
            BREAKER["failures"] = 0 if success else BREAKER["failures"] + 1
            if BREAKER["failures"] >= 3:
                BREAKER.update(state="open", opened_at=now)


def infer(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 5000:
        raise ValueError("Text must contain 1–5000 characters")
    if not ADMISSION.acquire(blocking=False):
        raise ValueError("Capacity reached: retry later (8 concurrent requests)")
    started = CLOCK()
    trace = uuid.uuid4().hex[:16]
    try:
        primary, probe = choose(started)
        with LOCK:
            failure = RNG.random() < CONFIG["failure_rate"]
            latency = CONFIG["latency_ms"]
        failed = False
        if primary:
            try:
                prediction = provider(text, True, failure, latency)
                settle(True, probe, CLOCK())
                route = "primary"
            except ProviderFailure:
                failed = True
                settle(False, probe, CLOCK())
                prediction = provider(text, False, False, 0)
                route = "fallback"
        else:
            prediction = provider(text, False, False, 0)
            route = "fallback"
        event = {
            "trace": trace,
            "route": route,
            "primary_failed": failed,
            "latency_ms": round((CLOCK() - started) * 1000, 2),
            "label": prediction["label"],
            "time": time.time(),
        }
        with LOCK:
            WINDOW.append(event)
            state = BREAKER["state"]
        return {**event, "model": prediction["model"], "breaker": state}
    finally:
        ADMISSION.release()


def configure(body):
    rate, latency = body.get("failure_rate"), body.get("latency_ms")
    if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("Failure rate must be between 0 and 1")
    if type(latency) is not int or not 0 <= latency <= 500:
        raise ValueError("Latency must be an integer from 0 to 500 ms")
    with LOCK:
        CONFIG.update(failure_rate=rate, latency_ms=latency)
    return snapshot()


def snapshot():
    with LOCK:
        events, config, breaker = list(WINDOW), dict(CONFIG), dict(BREAKER)
    values = sorted(e["latency_ms"] for e in events)
    fallback = sum(e["route"] == "fallback" for e in events)
    return {
        "config": config,
        "breaker": {"state": breaker["state"], "failures": breaker["failures"]},
        "events": events,
        "metrics": {
            "requests": len(events),
            "fallback_rate": fallback / len(events) if events else 0,
            "primary_failures": sum(e["primary_failed"] for e in events),
            "p95_ms": values[max(0, math.ceil(len(values) * 0.95) - 1)]
            if values
            else 0,
        },
    }


def handle(path, body):
    if path == "/api/infer":
        return infer(body.get("text"))
    if path == "/api/configure":
        return configure(body)
    raise ValueError("Unknown endpoint")
