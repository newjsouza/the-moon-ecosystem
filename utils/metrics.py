"""
utils/metrics.py
Metrics collection (Counters, Gauges, Histograms).
"""
import time
from typing import Dict, List, Callable

class MetricsCollector:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetricsCollector, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.counters: Dict[str, int] = {}
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = {}
        self.callbacks: List[Callable] = []
        self._initialized = True

    def inc_counter(self, name: str, value: int = 1):
        self.counters[name] = self.counters.get(name, 0) + value
        self._check_alerts(name, self.counters[name])

    def set_gauge(self, name: str, value: float):
        self.gauges[name] = value

    def observe_histogram(self, name: str, value: float):
        if name not in self.histograms:
            self.histograms[name] = []
        self.histograms[name].append(value)

    def add_alert_callback(self, callback: Callable):
        self.callbacks.append(callback)

    def _check_alerts(self, name: str, value: float):
        for cb in self.callbacks:
            try:
                cb(name, value)
            except Exception:
                pass

    def get_metrics(self) -> dict:
        return {
            "counters": self.counters,
            "gauges": self.gauges,
            "histograms": {k: {"count": len(v), "avg": sum(v)/len(v) if v else 0} for k, v in self.histograms.items()}
        }
