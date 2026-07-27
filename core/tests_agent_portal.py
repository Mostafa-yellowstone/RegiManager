from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.agent_portal_services import current_work_date, shift_close_at


NY = ZoneInfo("America/New_York")


class AgentPortalAttendanceMathTests(SimpleTestCase):
    def test_work_date_is_new_york_calendar_day(self):
        now = datetime(2026, 7, 22, 0, 30, tzinfo=NY)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-22")

    def test_work_date_during_day_is_same_calendar_day(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=NY)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-21")

    def test_shift_closes_at_6pm_same_day(self):
        work = current_work_date(datetime(2026, 7, 21, 9, 0, tzinfo=NY))
        close = shift_close_at(work)
        # EDT in July is UTC-4
        self.assertEqual(close.astimezone(NY).hour, 18)
        self.assertEqual(close.astimezone(NY).minute, 0)
        self.assertEqual(close.astimezone(NY).date().isoformat(), "2026-07-21")
