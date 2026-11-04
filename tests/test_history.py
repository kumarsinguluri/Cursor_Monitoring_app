import unittest

from app.history import SampleBuffer


class HistoryTests(unittest.TestCase):
    def test_append_keeps_values_in_order(self):
        buffer = SampleBuffer(retention_seconds=3600, max_points=10)
        buffer.append("cpu", 10, 1)
        buffer.append("cpu", 11, 2)
        buffer.append("memory", 40, 2)
        self.assertEqual(buffer.values("cpu"), [10.0, 11.0])
        self.assertEqual(buffer.values("memory"), [40.0])

    def test_cap_drops_the_oldest_points(self):
        buffer = SampleBuffer(retention_seconds=3600, max_points=3)
        for index in range(5):
            buffer.append("cpu", index, index)
        self.assertEqual(buffer.values("cpu"), [2.0, 3.0, 4.0])

    def test_expiry_drops_samples_older_than_the_window(self):
        buffer = SampleBuffer(retention_seconds=60, max_points=100)
        buffer.append("cpu", 1, 0)
        buffer.append("cpu", 2, 60)
        self.assertEqual(buffer.values("cpu"), [1.0, 2.0])
        buffer.append("cpu", 3, 61)
        self.assertEqual(buffer.values("cpu"), [2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
