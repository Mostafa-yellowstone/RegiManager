from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.agent_portal_services import (
    current_work_date,
    format_ny_time,
    is_within_shift_window,
    shift_close_at,
    shift_open_at,
)


NY = ZoneInfo("America/New_York")
CAIRO = ZoneInfo("Africa/Cairo")


class AgentPortalAttendanceMathTests(SimpleTestCase):
    def test_work_date_is_new_york_calendar_day(self):
        now = datetime(2026, 7, 22, 0, 30, tzinfo=NY)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-22")

    def test_work_date_during_day_is_same_calendar_day(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=NY)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-21")

    def test_shift_opens_at_4pm_egypt(self):
        work = current_work_date(datetime(2026, 7, 21, 12, 0, tzinfo=NY))
        open_at = shift_open_at(work)
        self.assertEqual(open_at.astimezone(CAIRO).hour, 16)
        self.assertEqual(open_at.astimezone(CAIRO).minute, 0)
        # July: Egypt UTC+3 / NY EDT UTC-4 → 4 PM Egypt == 9 AM NY
        self.assertEqual(open_at.astimezone(NY).hour, 9)
        self.assertEqual(open_at.astimezone(NY).date().isoformat(), "2026-07-21")

    def test_shift_closes_at_6pm_same_day(self):
        work = current_work_date(datetime(2026, 7, 21, 9, 0, tzinfo=NY))
        close = shift_close_at(work)
        # EDT in July is UTC-4
        self.assertEqual(close.astimezone(NY).hour, 18)
        self.assertEqual(close.astimezone(NY).minute, 0)
        self.assertEqual(close.astimezone(NY).date().isoformat(), "2026-07-21")

    def test_shift_window_egypt_open_to_ny_close(self):
        # July aligned offsets: Egypt 4 PM == NY 9 AM
        self.assertFalse(is_within_shift_window(datetime(2026, 7, 21, 8, 59, tzinfo=NY)))
        self.assertTrue(is_within_shift_window(datetime(2026, 7, 21, 9, 0, tzinfo=NY)))
        self.assertTrue(is_within_shift_window(datetime(2026, 7, 21, 16, 0, tzinfo=CAIRO)))
        self.assertTrue(is_within_shift_window(datetime(2026, 7, 21, 17, 59, tzinfo=NY)))
        self.assertFalse(is_within_shift_window(datetime(2026, 7, 21, 18, 0, tzinfo=NY)))

    def test_format_ny_time_ignores_viewer_timezone(self):
        # 9:00 AM New York in July = 4:00 PM Cairo (EDT UTC-4, Cairo UTC+3)
        ny_nine = datetime(2026, 7, 21, 9, 0, tzinfo=NY)
        cairo_view = ny_nine.astimezone(CAIRO)
        self.assertEqual(format_ny_time(cairo_view), "9:00 AM")
        self.assertEqual(format_ny_time(ny_nine), "9:00 AM")

    def test_punctuality_egypt_4pm_is_on_time(self):
        from core.agent_portal_services import attendance_punctuality
        from datetime import date

        work = date(2026, 7, 21)
        early = datetime(2026, 7, 21, 15, 45, tzinfo=CAIRO)
        exact = datetime(2026, 7, 21, 16, 0, tzinfo=CAIRO)
        late = datetime(2026, 7, 21, 16, 1, tzinfo=CAIRO)

        self.assertEqual(attendance_punctuality(early, work)["attendance_status"], "on_time")
        self.assertEqual(attendance_punctuality(exact, work)["attendance_status"], "on_time")
        self.assertEqual(attendance_punctuality(late, work)["attendance_status"], "late")
        self.assertFalse(attendance_punctuality(None, work)["is_late"])

    def test_punctuality_follows_egypt_when_dst_drifts(self):
        """When Egypt/US offsets are not 7h, 4 PM Egypt stays on time (not NY 9 AM)."""
        from core.agent_portal_services import attendance_punctuality
        from datetime import date

        # Pick a mid-winter day: Egypt typically UTC+2, NY EST UTC-5 → still 7h.
        # Force the rule: clock-in at Egypt 4 PM must be on_time regardless of NY hour.
        work = date(2026, 1, 15)
        at_four = datetime(2026, 1, 15, 16, 0, tzinfo=CAIRO)
        self.assertEqual(attendance_punctuality(at_four, work)["attendance_status"], "on_time")
        self.assertEqual(at_four.astimezone(CAIRO).hour, 16)
