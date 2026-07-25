from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.agent_portal_services import current_work_date, shift_close_at


CAIRO = ZoneInfo("Africa/Cairo")


class AgentPortalAttendanceMathTests(SimpleTestCase):
    def test_work_date_before_1am_belongs_to_previous_day(self):
        now = datetime(2026, 7, 22, 0, 30, tzinfo=CAIRO)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-21")

    def test_work_date_after_1am_is_same_calendar_day(self):
        now = datetime(2026, 7, 21, 9, 0, tzinfo=CAIRO)
        self.assertEqual(current_work_date(now).isoformat(), "2026-07-21")

    def test_shift_closes_at_1am_next_day(self):
        work = current_work_date(datetime(2026, 7, 21, 9, 0, tzinfo=CAIRO))
        close = shift_close_at(work)
        self.assertEqual(close.astimezone(CAIRO).isoformat(), "2026-07-22T01:00:00+03:00")
