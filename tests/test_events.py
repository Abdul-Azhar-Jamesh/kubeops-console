import unittest
from unittest.mock import patch

from dashboard.main import page, related_events


class EventTests(unittest.TestCase):
    def events(self, items):
        with patch("dashboard.main.read", return_value={"items": items}):
            return related_events([("Pod", {"metadata": {"name": "web", "uid": "current-uid"}})])

    def event(self, uid="current-uid", **fields):
        return {"involvedObject": {"uid": uid, "name": "web"}, **fields}

    def test_name_reuse_and_unrelated_events_are_excluded(self):
        events = self.events([self.event(reason="Scheduled"), self.event("old-uid"), self.event("unrelated-uid"), {}])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["object"], "Pod/web")
        self.assertEqual(events[0]["reason"], "Scheduled")

    def test_latest_observation_and_series_count(self):
        events = self.events([
            self.event(lastTimestamp="2026-11-22T10:00:00Z", reason="older"),
            self.event(eventTime="2026-11-22T10:00:00.100000Z", reason="newer"),
            {"regarding": {"uid": "current-uid"}, "note": "repeated event", "series": {
                "lastObservedTime": "2026-11-22T10:01:00Z", "count": 7}},
        ])
        self.assertEqual(events[0]["count"], 7)
        self.assertEqual(events[0]["message"], "repeated event")
        self.assertEqual([e["reason"] for e in events[1:]], ["newer", "older"])

    def test_missing_times_and_output_limits(self):
        events = self.events([self.event(message="x" * 5000) for _ in range(60)])
        self.assertEqual(len(events), 50)
        self.assertEqual(len(events[0]["message"]), 2000)
        self.assertEqual(events[0]["time"], "Unknown")
        self.assertEqual(events[0]["count"], 1)

    def test_event_markup_is_escaped_and_empty_state_is_visible(self):
        data = {"image": "test:v1", "ready": 1, "desired": 1, "service": "10.0.0.1", "pods": []}
        self.assertIn("No related events retained", page(data))
        data["events"] = self.events([self.event(message="<script>bad()</script>", reason='<img src="bad">')])
        html = page(data)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
