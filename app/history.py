"""In-memory metric samples. Nothing here is written to disk."""

import threading

SAMPLE_INTERVAL_SECONDS = 5
HISTORY_SECONDS = 60 * 60
MAX_POINTS = HISTORY_SECONDS // SAMPLE_INTERVAL_SECONDS


class SampleBuffer:
    """Keep one series of samples for at most HISTORY_SECONDS, capped at MAX_POINTS."""

    def __init__(self, retention_seconds=HISTORY_SECONDS, max_points=MAX_POINTS):
        if retention_seconds <= 0 or max_points < 1:
            raise ValueError("retention and cap must be positive")
        self.retention_seconds = float(retention_seconds)
        self.max_points = int(max_points)
        self._series = {}
        self._lock = threading.Lock()

    def append(self, key, value, now):
        point = (float(now), float(value))
        with self._lock:
            points = self._series.setdefault(key, [])
            points.append(point)
            cutoff = point[0] - self.retention_seconds
            if points[0][0] < cutoff or len(points) > self.max_points:
                kept = [item for item in points if item[0] >= cutoff]
                if len(kept) > self.max_points:
                    kept = kept[-self.max_points :]
                self._series[key] = kept

    def series(self, key):
        with self._lock:
            return list(self._series.get(key, ()))

    def values(self, key):
        return [value for _, value in self.series(key)]
