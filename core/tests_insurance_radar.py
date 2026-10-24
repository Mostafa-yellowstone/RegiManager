from datetime import timedelta
from decimal import Decimal
from itertools import count

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.insurance_producers import add_months
from core.insurance_radar import radar_summary, scoreboard, sync_radar
from core.models import (
    Client,
    InsuranceCompany,
    InsurancePolicy,
    InsuranceRadarItem,
    Notification,
    Organization,
    OrganizationMembership,
    ServiceRecord,
    Space,
    Vehicle,
)

Signal = InsuranceRadarItem.Signal
_receipts = count(1)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RadarBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.org = Organization.objects.create(name="Radar Org", has_psb_portal=True, has_insurance=True)
        Space.objects.create(organization=self.org, key="insurance", label="Insurance")
        self.owner = User.objects.create_user(username="rd-owner", password="x")
        self.agent = User.objects.create_user(username="rd-agent", password="x", first_name="Ina", last_name="Agent")
        self.dmv = User.objects.create_user(username="rd-dmv", password="x", first_name="Dan", last_name="Dmv")
        OrganizationMembership.objects.create(
            user=self.owner, organization=self.org, role=OrganizationMembership.Role.OWNER, is_active=True,
            can_use_insurance=True, can_use_psb_portal=True,
        )
        OrganizationMembership.objects.create(
            user=self.agent, organization=self.org, role=OrganizationMembership.Role.AGENT, is_active=True,
            can_use_insurance=True, can_deal_with_insurance=True,
        )
        OrganizationMembership.objects.create(
            user=self.dmv, organization=self.org, role=OrganizationMembership.Role.AGENT, is_active=True,
            can_use_insurance=False, can_use_psb_portal=True,
        )
        self.company = InsuranceCompany.objects.create(organization=self.org, name="Acme")
        self.customer = Client.objects.create(organization=self.org, first_name="Mia", last_name="Stone", phone_number="7185550199")

    def vehicle(self, vin="1HGCM82633A004352", plate="ABC123", client=None, **extra):
        return Vehicle.objects.create(client=client or self.customer, vin=vin, plate_number=plate, make="Honda", **extra)

    def record(self, vehicle, service_type="vehicle_registration", days_ago=3, **extra):
        return ServiceRecord.objects.create(
            organization=self.org,
            handled_by=extra.pop("handled_by", self.dmv),
            vehicle=vehicle,
            service_type=service_type,
            transaction_date=self.today - timedelta(days=days_ago),
            receipt_number=f"RD-{next(_receipts)}",
            **extra,
        )

    def policy(self, number="P-1", client=None, **extra):
        end = self.today + timedelta(days=120)
        return InsurancePolicy.objects.create(
            organization=self.org, client=client or self.customer, policy_number=number, insurance_company=self.company,
            premium=Decimal("1000"), start_date=add_months(end, -6), end_date=end, bound_date=add_months(end, -6),
            stage="bound", status="active", insurance_type="auto_personal", added_by=self.agent, **extra,
        )

    def signals(self):
        return set(InsuranceRadarItem.objects.values_list("signal", flat=True))


class SyncTests(RadarBase):
    def test_new_registration_for_uninsured_vehicle_credits_the_dmv_agent(self):
        car = self.vehicle()
        self.record(car)
        self.record(car, days_ago=45)

        sync_radar(self.org, today=self.today)

        item = InsuranceRadarItem.objects.get()
        self.assertEqual(item.signal, Signal.NEW_REGISTRATION)
        self.assertEqual(item.vehicle, car)
        self.assertEqual(item.referred_by, self.dmv)
        self.assertIsNone(item.assigned_to)

        sync_radar(self.org, today=self.today)
        self.assertEqual(InsuranceRadarItem.objects.count(), 1)

    def test_insured_vehicle_is_skipped(self):
        car = self.vehicle()
        self.policy(plate_number="abc123")
        self.record(car)
        sync_radar(self.org, today=self.today)
        self.assertFalse(InsuranceRadarItem.objects.exists())

    def test_outside_insurance_expiring(self):
        self.vehicle(insurance_company="Geico", insurance_expiration_date=self.today + timedelta(days=20))
        self.vehicle(vin="FAR", plate="FAR1", insurance_company="Geico", insurance_expiration_date=self.today + timedelta(days=90))
        sync_radar(self.org, today=self.today)
        self.assertEqual(self.signals(), {Signal.OUTSIDE_EXPIRING})

    def test_registration_renewal_only_for_clients_without_insurance(self):
        self.vehicle(registration_expiration_date=self.today + timedelta(days=10))
        other = Client.objects.create(organization=self.org, first_name="Al", last_name="Ins")
        self.policy("P-OTHER", client=other)
        self.vehicle(vin="V2", plate="P2", client=other, registration_expiration_date=self.today + timedelta(days=10))

        sync_radar(self.org, today=self.today)
        items = InsuranceRadarItem.objects.filter(signal=Signal.REGISTRATION_RENEWAL)
        self.assertEqual([i.client for i in items], [self.customer])

    def test_surrendered_plates_on_insured_vehicle(self):
        car = self.vehicle()
        policy = self.policy(vin=car.vin)
        self.record(car, service_type="surrender_plates")
        sync_radar(self.org, today=self.today)
        item = InsuranceRadarItem.objects.get(signal=Signal.PLATES_SURRENDERED)
        self.assertEqual(item.policy, policy)

    def test_dmv_only_client(self):
        boat = self.vehicle(vehicle_type="boat")
        self.record(boat, service_type="duplicate_title")
        sync_radar(self.org, today=self.today)
        self.assertEqual(self.signals(), {Signal.DMV_ONLY})

    def test_insurance_only_office_has_no_radar(self):
        self.org.has_psb_portal = False
        self.org.save(update_fields=["has_psb_portal"])
        self.record(self.vehicle())
        sync_radar(self.org, today=self.today)
        self.assertFalse(InsuranceRadarItem.objects.exists())
        self.client.force_login(self.owner)
        self.assertNotEqual(self.client.get(reverse("insurance-radar")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("insurance-home")), reverse("insurance-radar"))


class WorkflowTests(RadarBase):
    def setUp(self):
        super().setUp()
        self.record(self.vehicle())
        sync_radar(self.org, today=self.today)
        self.item = InsuranceRadarItem.objects.get()

    def test_manager_assigns_and_agent_gets_bell(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("insurance-radar-bulk-assign"), {"items": [self.item.id], "assigned_to": self.agent.id}
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.assigned_to, self.agent)
        self.assertTrue(Notification.objects.filter(user=self.agent, event_type="insurance_radar_assigned").exists())

    def test_agents_only_see_and_work_their_items(self):
        self.client.force_login(self.agent)
        card = f'href="{reverse("client-detail", args=[self.customer.id])}">Mia Stone'
        self.assertNotContains(self.client.get(reverse("insurance-radar")), card)
        resp = self.client.post(reverse("insurance-radar-action", args=[self.item.id]), {"action": "dismiss"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(
            reverse("insurance-radar-action", args=[self.item.id]), {"action": "assign", "assigned_to": self.agent.id}
        )
        self.assertEqual(resp.status_code, 403)

        self.item.assigned_to = self.agent
        self.item.save()
        self.assertContains(self.client.get(reverse("insurance-radar")), card)
        self.client.post(
            reverse("insurance-radar-action", args=[self.item.id]), {"action": "done", "won": "1", "note": "Bound auto"}
        )
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.won, self.item.note), ("done", True, "Bound auto"))

    def test_nothing_goes_to_the_quote_pipeline(self):
        from core.models import InsuranceQuoteLead

        self.client.force_login(self.owner)
        self.client.post(reverse("insurance-radar-action", args=[self.item.id]), {"action": "done", "won": "1"})
        self.assertFalse(InsuranceQuoteLead.objects.exists())

    def test_reopen_and_scoreboard(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("insurance-radar-action", args=[self.item.id]), {"action": "done", "won": "1"})
        row = scoreboard(self.org)[0]
        self.assertEqual((row.user, row.referred, row.won, row.rate), (self.dmv, 1, 1, 100))

        self.client.post(reverse("insurance-radar-action", args=[self.item.id]), {"action": "reopen"})
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.won), ("open", False))

    def test_today_board_and_client_profile_show_radar(self):
        summary = radar_summary(self.org, self.owner, manager=True)
        self.assertEqual((summary["open_total"], summary["unassigned"]), (1, 1))
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("insurance-home")), "DMV radar")
        self.assertContains(self.client.get(reverse("client-detail", args=[self.customer.id])), 'id="radar"')
        self.assertContains(self.client.get(reverse("insurance-radar")), "Cross-sell scoreboard")
