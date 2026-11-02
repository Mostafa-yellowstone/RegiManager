from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.test import Client as TestClient
from django.urls import reverse

from core.models import Organization, OrganizationMembership, ServiceRecord


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AgentAuditTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Audit Org", city="NYC")
        self.owner = User.objects.create_user(username="auditowner", password="password123", first_name="Owen")
        self.agent_user = User.objects.create_user(username="audithand", password="password123", first_name="Ada", last_name="Lane")
        OrganizationMembership.objects.create(
            user=self.owner,
            organization=self.org,
            is_active=True,
            role="owner",
            can_view_spaces=True,
        )
        self.agent = OrganizationMembership.objects.create(
            user=self.agent_user,
            organization=self.org,
            is_active=True,
            role="agent",
            can_view_spaces=True,
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent_user,
            service_type="vehicle_registration",
            status="completed",
            client_name="January Client",
            receipt_number="RCPT-AUDIT-JAN",
            transaction_date=date(2026, 1, 15),
            dmv_fee=Decimal("25.00"),
            processing_fee=Decimal("15.00"),
            plate_number="JAN111",
        )
        ServiceRecord.objects.create(
            organization=self.org,
            handled_by=self.agent_user,
            service_type="new_plates",
            status="failed",
            client_name="March Client",
            receipt_number="RCPT-AUDIT-MAR",
            transaction_date=date(2026, 3, 2),
            dmv_fee=Decimal("50.00"),
            processing_fee=Decimal("30.00"),
            plate_number="MAR222",
        )
        self.client = TestClient()
        self.client.login(username="auditowner", password="password123")

    def test_directory_and_profile_cover_the_whole_window(self):
        directory = self.client.get(reverse("all-agents-directory"), {"period": "all"})
        self.assertEqual(directory.status_code, 200)
        self.assertContains(directory, "Ada Lane")
        self.assertContains(directory, "All time")
        self.assertContains(directory, "Open audit")

        profile = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all"},
        )
        self.assertEqual(profile.status_code, 200)
        self.assertContains(profile, "RCPT-AUDIT-JAN")
        self.assertContains(profile, "RCPT-AUDIT-MAR")
        self.assertContains(profile, "Export Excel")

        january = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "custom", "start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        self.assertContains(january, "RCPT-AUDIT-JAN")
        self.assertNotContains(january, "RCPT-AUDIT-MAR")

        exported = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "export": "xlsx"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("spreadsheetml", exported["Content-Type"])
        self.assertIn(b"PK", exported.content[:2])

    def test_advanced_audit_filters_service_type_payment_fee_notes(self):
        # Service type filter
        resp_service = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "service_type": "vehicle_registration"},
        )
        self.assertEqual(resp_service.status_code, 200)
        self.assertContains(resp_service, "RCPT-AUDIT-JAN")
        self.assertNotContains(resp_service, "RCPT-AUDIT-MAR")

        # Status filter
        resp_status = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "status": "failed"},
        )
        self.assertEqual(resp_status.status_code, 200)
        self.assertContains(resp_status, "RCPT-AUDIT-MAR")
        self.assertNotContains(resp_status, "RCPT-AUDIT-JAN")

        # Fee range filter
        resp_fee = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "min_fee": "50.00"},
        )
        self.assertEqual(resp_fee.status_code, 200)
        self.assertContains(resp_fee, "RCPT-AUDIT-MAR")
        self.assertNotContains(resp_fee, "RCPT-AUDIT-JAN")

        # Sorting filter
        resp_sort = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "sort": "-service_fee"},
        )
        self.assertEqual(resp_sort.status_code, 200)
        page_records = list(resp_sort.context["page_obj"])
        self.assertEqual(page_records[0].receipt_number, "RCPT-AUDIT-MAR")
        self.assertEqual(page_records[1].receipt_number, "RCPT-AUDIT-JAN")

    def test_audit_active_chips_and_tab_counter(self):
        resp = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "audit", "period": "all", "status": "failed", "min_fee": "50.00"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["active_filters_count"], 2)
        chip_keys = {c["key"] for c in resp.context["active_chips"]}
        self.assertEqual(chip_keys, {"status", "min_fee"})
        self.assertContains(resp, "audit-chip")
        self.assertContains(resp, "uap-tab-count")

    def test_all_agents_directory_filtration_and_sorting(self):
        # Create second agent with insurance role and no records
        ins_user = User.objects.create_user(username="insagent", password="password123", first_name="Zoe", last_name="Vance")
        OrganizationMembership.objects.create(
            user=ins_user,
            organization=self.org,
            is_active=True,
            role="insurance_agent",
            can_view_spaces=True,
        )

        # Baseline view: both agents present
        resp_all = self.client.get(reverse("all-agents-directory"), {"period": "all"})
        self.assertEqual(resp_all.status_code, 200)
        self.assertEqual(len(resp_all.context["agent_data"]), 2)
        self.assertEqual(resp_all.context["team_total_records"], 2)
        self.assertEqual(resp_all.context["team_total_failed"], 1)

        # Filter by role: insurance_agent only
        resp_role = self.client.get(reverse("all-agents-directory"), {"period": "all", "role": "insurance_agent"})
        self.assertEqual(len(resp_role.context["agent_data"]), 1)
        self.assertEqual(resp_role.context["agent_data"][0]["name"], "Zoe Vance")

        # Filter by activity: active only (has records) -> Ada Lane
        resp_active = self.client.get(reverse("all-agents-directory"), {"period": "all", "activity": "active"})
        self.assertEqual(len(resp_active.context["agent_data"]), 1)
        self.assertEqual(resp_active.context["agent_data"][0]["name"], "Ada Lane")

        # Filter by activity: has_errors -> Ada Lane (1 failed)
        resp_errors = self.client.get(reverse("all-agents-directory"), {"period": "all", "activity": "has_errors"})
        self.assertEqual(len(resp_errors.context["agent_data"]), 1)
        self.assertEqual(resp_errors.context["agent_data"][0]["name"], "Ada Lane")

        # Filter by activity: inactive (0 records) -> Zoe Vance
        resp_inactive = self.client.get(reverse("all-agents-directory"), {"period": "all", "activity": "inactive"})
        self.assertEqual(len(resp_inactive.context["agent_data"]), 1)
        self.assertEqual(resp_inactive.context["agent_data"][0]["name"], "Zoe Vance")

        # Sort by name
        resp_sort_name = self.client.get(reverse("all-agents-directory"), {"period": "all", "sort": "name"})
        names = [d["name"] for d in resp_sort_name.context["agent_data"]]
        self.assertEqual(names, ["Ada Lane", "Zoe Vance"])

    def test_insurance_agent_profile_audits_insurance_only(self):
        from core.models import Client, InsuranceCompany, InsurancePolicy

        ins_user = User.objects.create_user(username="insauditor", password="password123", first_name="Irene", last_name="Spears")
        ins_member = OrganizationMembership.objects.create(
            user=ins_user,
            organization=self.org,
            is_active=True,
            role="insurance_agent",
            can_view_spaces=True,
        )
        test_client = Client.objects.create(
            organization=self.org,
            first_name="Insured",
            last_name="Client",
            phone_number="555-123-4567",
        )
        company = InsuranceCompany.objects.create(
            organization=self.org,
            name="Apex Underwriters",
        )
        today = date.today()
        # Today's bound policy
        p_today = InsurancePolicy.objects.create(
            organization=self.org,
            client=test_client,
            policy_number="POL-TODAY-001",
            insurance_company=company,
            premium=Decimal("1500.00"),
            broker_fee=Decimal("100.00"),
            stage="bound",
            status="active",
            insurance_type="auto_personal",
            bound_date=today,
            start_date=today,
            end_date=date(today.year + 1, today.month, today.day),
            added_by=ins_user,
        )
        # Year past quote policy
        p_past = InsurancePolicy.objects.create(
            organization=self.org,
            client=test_client,
            policy_number="POL-PAST-002",
            insurance_company=company,
            premium=Decimal("800.00"),
            broker_fee=Decimal("50.00"),
            stage="quote",
            status="pending",
            insurance_type="commercial_auto",
            bound_date=date(today.year - 1, 6, 15) if today.month < 7 else date(today.year, 1, 10),
            start_date=date(today.year - 1, 6, 15) if today.month < 7 else date(today.year, 1, 10),
            end_date=date(today.year, 6, 15) if today.month < 7 else date(today.year + 1, 1, 10),
            added_by=ins_user,
        )

        # Access insurance agent profile
        resp = self.client.get(reverse("agent-profile", args=[ins_member.id]))
        self.assertEqual(resp.status_code, 200)

        # Service audit must NOT be in navigation for insurance agents
        self.assertNotContains(resp, "Service audit")
        self.assertContains(resp, "Insurance audit")

        # Dummy placeholder button must be gone
        self.assertNotContains(resp, "Open insurance policy CRM")

        # Period filtering: Today (day)
        resp_today = self.client.get(
            reverse("agent-profile", args=[ins_member.id]),
            {"tab": "insurance", "period": "today"},
        )
        self.assertEqual(resp_today.status_code, 200)
        self.assertContains(resp_today, "POL-TODAY-001")
        if p_past.bound_date != today:
            self.assertNotContains(resp_today, "POL-PAST-002")

        # Period filtering: Year
        resp_year = self.client.get(
            reverse("agent-profile", args=[ins_member.id]),
            {"tab": "insurance", "period": "year"},
        )
        self.assertEqual(resp_year.status_code, 200)
        self.assertContains(resp_year, "POL-TODAY-001")

        # Multi-dimensional filter: stage=bound, min_premium=1000
        resp_filter = self.client.get(
            reverse("agent-profile", args=[ins_member.id]),
            {"tab": "insurance", "period": "all", "stage": "bound", "min_premium": "1000.00"},
        )
        self.assertEqual(resp_filter.status_code, 200)
        self.assertContains(resp_filter, "POL-TODAY-001")
        self.assertNotContains(resp_filter, "POL-PAST-002")
        self.assertEqual(resp_filter.context["ins_active_filters_count"], 2)
        self.assertContains(resp_filter, "audit-chip")

        # Pagination must not contain pager-looking text
        self.assertNotContains(resp, "Page 1 of")
        self.assertNotContains(resp, "1 / ")

    def test_insurance_policy_actions_preserve_filter_state(self):
        from core.models import Client, InsuranceCompany, InsurancePolicy

        client = Client.objects.create(
            organization=self.org,
            first_name="Filter",
            last_name="Preserve",
        )
        company = InsuranceCompany.objects.create(
            organization=self.org,
            name="SafeCo",
        )
        policy = InsurancePolicy.objects.create(
            organization=self.org,
            client=client,
            policy_number="POL-DEL-999",
            insurance_company=company,
            premium=Decimal("950.00"),
            stage="quote",
            status="active",
            bound_date=date.today(),
            start_date=date.today(),
            end_date=date(date.today().year + 1, date.today().month, date.today().day),
            added_by=self.owner,
        )

        filter_url = "/dashboard/spaces/insurance/policies/?status=active&stage=quote&insurance_type=auto_personal&page=1"
        resp_del = self.client.post(
            reverse("delete-insurance-policy", args=[policy.id]),
            {"next": filter_url},
        )
        # Should redirect back to the exact filtered CRM URL
        self.assertEqual(resp_del.status_code, 302)
        self.assertEqual(resp_del.url, filter_url)

    def test_monthly_attendance_saved_and_profile_metrics(self):
        from core.agent_portal_models import AgentAttendanceSession
        from core.agent_portal_services import monthly_attendance_for_membership
        from zoneinfo import ZoneInfo
        from datetime import datetime, time

        ny_tz = ZoneInfo("America/New_York")
        d1 = date(2026, 11, 2)  # Monday
        d2 = date(2026, 11, 3)  # Tuesday

        s1 = AgentAttendanceSession.objects.create(
            membership=self.agent,
            organization=self.org,
            work_date=d1,
            opened_at=datetime.combine(d1, time(9, 0), tzinfo=ny_tz),
            closed_at=datetime.combine(d1, time(18, 0), tzinfo=ny_tz),
        )
        s2 = AgentAttendanceSession.objects.create(
            membership=self.agent,
            organization=self.org,
            work_date=d2,
            opened_at=datetime.combine(d2, time(9, 15), tzinfo=ny_tz),
            closed_at=datetime.combine(d2, time(17, 30), tzinfo=ny_tz),
        )

        att = monthly_attendance_for_membership(self.agent, year=2026, month=11)
        self.assertEqual(att["days_attended"], 2)
        self.assertGreaterEqual(att["days_left_in_month"], 0)
        self.assertEqual(att["month_label"], "November 2026")

        # Open agent profile with tab=attendance
        resp = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "attendance", "attendance_year": "2026", "attendance_month": "11"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Monthly Attendance Tracker")
        self.assertContains(resp, "Days Attended")
        self.assertContains(resp, "Days Left in Month")

        # Also test Overview tab has attendance pulse
        resp_overview = self.client.get(
            reverse("agent-profile", args=[self.agent.id]),
            {"tab": "overview"},
        )
        self.assertEqual(resp_overview.status_code, 200)
        self.assertContains(resp_overview, "Monthly Attendance Pulse")

    def test_save_agent_attendance_session_manual(self):
        from core.agent_portal_models import AgentAttendanceSession

        test_date = "2026-11-04"
        resp = self.client.post(
            reverse("agent-attendance-save", args=[self.agent.id]),
            {
                "work_date": test_date,
                "opened_time": "09:10",
                "closed_time": "18:00",
            },
        )
        self.assertEqual(resp.status_code, 302)

        session = AgentAttendanceSession.objects.filter(
            membership=self.agent,
            work_date=date(2026, 11, 4),
        ).first()
        self.assertIsNotNone(session)
        from zoneinfo import ZoneInfo
        ny_tz = ZoneInfo("America/New_York")
        self.assertEqual(session.opened_at.astimezone(ny_tz).hour, 9)
        self.assertEqual(session.opened_at.astimezone(ny_tz).minute, 10)
        self.assertIsNotNone(session.closed_at)
