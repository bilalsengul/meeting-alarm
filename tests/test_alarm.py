import datetime as dt
import os
import sys
import tempfile
import unittest

_HOME = tempfile.mkdtemp(prefix="meeting-alarm-test-")
os.environ["MEETING_ALARM_HOME"] = _HOME  # must be set before importing alarm
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import alarm  # noqa: E402
import strings  # noqa: E402

START = dt.datetime(2030, 1, 1, 12, 0, tzinfo=dt.timezone.utc)
_REAL = (alarm.now_utc, alarm.now_ts, alarm.upcoming, alarm.show_overlay, alarm.log)


class FakeClock:
    def __init__(self, at: dt.datetime) -> None:
        self.now = at

    def set(self, at: dt.datetime) -> None:
        self.now = at

    def utc(self) -> dt.datetime:
        return self.now

    def ts(self) -> float:
        return self.now.timestamp()


def _restore() -> None:
    alarm.now_utc, alarm.now_ts, alarm.upcoming, alarm.show_overlay, alarm.log = _REAL


class TickBase(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(_restore)
        self.clock = FakeClock(START)
        self.fires: list[dict] = []
        self.rcs: list[int] = []  # queued overlay exit codes; default 0
        self.ev = {"key": "evt@2030-01-01T12:00:00+00:00", "title": "Sync", "start": START,
                   "link": "https://meet.google.com/abc", "organizer": "a@example.com"}
        self.cfg = dict(alarm.DEFAULTS)
        self.state: dict = {}
        alarm.now_utc = self.clock.utc
        alarm.now_ts = self.clock.ts
        alarm.upcoming = lambda cfg: [self.ev]
        alarm.show_overlay = self._overlay
        alarm.log = lambda msg: None

    def _overlay(self, payload: dict) -> int:
        self.fires.append(payload)
        return self.rcs.pop(0) if self.rcs else 0

    def at(self, minutes_from_start: float) -> None:
        self.clock.set(START + dt.timedelta(minutes=minutes_from_start))

    def tick(self) -> None:
        alarm.tick(self.cfg, self.state)


class JoinLinkTests(unittest.TestCase):
    def test_precedence(self) -> None:
        ev = {"hangoutLink": "https://meet.google.com/h",
              "conferenceData": {"entryPoints": [{"entryPointType": "video", "uri": "https://c.example/v"}]},
              "description": "https://zoom.us/j/1"}
        self.assertEqual(alarm.join_link(ev), "https://meet.google.com/h")
        del ev["hangoutLink"]
        self.assertEqual(alarm.join_link(ev), "https://c.example/v")
        del ev["conferenceData"]
        self.assertEqual(alarm.join_link(ev), "https://zoom.us/j/1")
        ev["description"] = "see https://teams.microsoft.com/l/meetup-join/x ok"
        self.assertEqual(alarm.join_link(ev), "https://teams.microsoft.com/l/meetup-join/x")
        self.assertEqual(alarm.join_link({"description": "nothing here"}), "")


class LeadsTests(unittest.TestCase):
    def test_always_zero_sorted_deduped(self) -> None:
        self.assertEqual(alarm.leads({"lead_minutes": [1, 10, 5, 5, 10]}), [10, 5, 1, 0])
        self.assertEqual(alarm.leads({"lead_minutes": []}), [0])
        self.assertIn(0, alarm.leads({"lead_minutes": [5]}))


class TickTests(TickBase):
    def test_heads_up_fires_once(self) -> None:
        self.at(-5)
        self.tick()
        self.tick()
        self.at(-4)
        self.tick()
        self.assertEqual(len(self.fires), 1)
        self.assertIn("5 min", self.fires[0]["subtitle"])
        self.assertEqual(self.fires[0]["join_label"], strings.t("en", "join"))

    def test_pre_alert_dismissed_start_still_fires(self) -> None:
        self.at(-5)
        self.tick()
        self.assertFalse(self.state[self.ev["key"]]["done"])
        self.at(0)
        self.tick()
        self.assertEqual(len(self.fires), 2)
        self.assertIn("NOW", self.fires[1]["subtitle"])

    def test_snooze_never_past_start(self) -> None:
        self.at(-1.5)
        self.rcs = [20]
        self.tick()
        snooze_until = self.state[self.ev["key"]]["snooze_until"]
        self.assertLessEqual(snooze_until, START.timestamp())
        self.at(0)
        self.tick()
        self.assertEqual(len(self.fires), 2)

    def test_join_is_final(self) -> None:
        self.at(-5)
        self.rcs = [10]
        self.tick()
        self.assertTrue(self.state[self.ev["key"]]["done"])
        for m in (0, 2, 5, 10):
            self.at(m)
            self.tick()
        self.assertEqual(len(self.fires), 1)

    def test_crash_at_start_repeats_then_stops(self) -> None:
        self.rcs = [1] * 10
        self.at(0)
        self.tick()  # lead 5 slot
        self.tick()  # lead 0 slot
        self.assertEqual(len(self.fires), 2)
        self.at(1)
        self.tick()
        self.assertEqual(len(self.fires), 2)
        self.at(2)
        self.tick()
        self.assertEqual(len(self.fires), 3)
        self.at(4)
        self.tick()
        self.assertEqual(len(self.fires), 4)
        self.at(16)
        self.tick()
        self.assertEqual(len(self.fires), 4)


class PruneTests(unittest.TestCase):
    def test_drops_old_keys(self) -> None:
        self.addCleanup(_restore)
        alarm.now_utc = FakeClock(START).utc
        old = (START - dt.timedelta(days=2)).isoformat()
        new = (START - dt.timedelta(hours=1)).isoformat()
        state = {f"a@{old}": {}, f"b@{new}": {}, "no-at-sign": {}}
        alarm.prune(state)
        self.assertEqual(list(state), [f"b@{new}"])


class StringsTests(unittest.TestCase):
    def test_keys_match_across_languages(self) -> None:
        required = {"header", "starts_in", "starts_now", "in_progress", "untitled", "join", "ok", "snooze",
                    "dismiss", "hint", "test_title", "test_subtitle", "auth_page_ok", "auth_page_nocode"}
        self.assertEqual(required, set(strings.STRINGS["en"]))
        self.assertEqual(required, set(strings.STRINGS["tr"]))

    def test_fallback_and_format(self) -> None:
        self.assertEqual(strings.t("xx", "join"), strings.t("en", "join"))
        self.assertEqual(strings.t("tr", "nope"), "nope")
        self.assertEqual(strings.t("en", "snooze", minutes=3), "Snooze 3 min  (Space)")
        self.assertNotEqual(strings.t("tr", "header"), strings.t("en", "header"))


class JoinLinkSchemeTests(unittest.TestCase):
    def test_non_http_schemes_are_dropped(self):
        self.assertEqual(alarm.join_link({"hangoutLink": "javascript:alert(1)"}), "")
        self.assertEqual(alarm.join_link({"conferenceData": {"entryPoints": [
            {"entryPointType": "video", "uri": "file:///etc/passwd"}]}}), "")
        self.assertEqual(alarm.join_link({"hangoutLink": "ftp://x", "description": "https://zoom.us/j/1"}),
                         "https://zoom.us/j/1")


if __name__ == "__main__":
    unittest.main()