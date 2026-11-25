"""Step-by-step follow-up for one quote: what is done, what is next, who did it."""
from django.conf import settings
from django.db import models
from django.utils import timezone

STEPS = [
    ("data_entry", "Data entry", "Lead details complete and validated"),
    ("consent", "Customer consent", "Consumer-report disclosure given, customer agrees to CLUE/MVR pull"),
    ("run_quote", "Run quote", "Carriers run, rates returned"),
    ("mvr", "Run MVR / Point of Sale", "CLUE and MVR ordered, post-POS rate checked"),
    ("send_quote", "Send quote to customer", "Quote summary sent"),
    ("verification", "Pre-bind verification", "Documents/PBV requested by the carrier handled"),
    ("decision", "Customer decision", "Customer accepts or declines"),
    ("bind", "Bind and payment", "Policy bound and first payment taken (human only)"),
]
STEP_KEYS = [s[0] for s in STEPS]


class QuoteFollowUpStep(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE = "done", "Done"
        BLOCKED = "blocked", "Blocked"
        SKIPPED = "skipped", "Skipped"

    lead = models.ForeignKey("InsuranceQuoteLead", on_delete=models.CASCADE, related_name="followup_steps")
    key = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=300, blank=True, default="")
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    done_by_system = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lead", "key"], name="uniq_followup_step_per_lead")]

    @property
    def label(self):
        return next(s[1] for s in STEPS if s[0] == self.key)

    @property
    def help(self):
        return next(s[2] for s in STEPS if s[0] == self.key)


def ensure_steps(lead):
    for k in STEP_KEYS:
        QuoteFollowUpStep.objects.get_or_create(lead=lead, key=k)
    order = {k: i for i, k in enumerate(STEP_KEYS)}
    return sorted(lead.followup_steps.all(), key=lambda s: order[s.key])


def mark_step(lead, key, status, user=None, note="", system=False):
    """Set a step. A step cannot be marked done while an earlier step is still pending or blocked."""
    if key not in STEP_KEYS:
        raise ValueError("Unknown step")
    steps = {s.key: s for s in ensure_steps(lead)}
    if status == QuoteFollowUpStep.Status.DONE:
        for k in STEP_KEYS[: STEP_KEYS.index(key)]:
            if steps[k].status in (QuoteFollowUpStep.Status.PENDING, QuoteFollowUpStep.Status.BLOCKED):
                raise ValueError(f"Finish '{steps[k].label}' first.")
    if key == "bind" and system:
        raise ValueError("Binding is a human step.")
    s = steps[key]
    s.status = status
    s.note = note[:300]
    s.done_by = user if (user and not system) else None
    s.done_by_system = system
    s.done_at = timezone.now() if status != QuoteFollowUpStep.Status.PENDING else None
    s.save()
    return s


def consent_given(lead) -> bool:
    s = lead.followup_steps.filter(key="consent").first()
    return bool(s and s.status == QuoteFollowUpStep.Status.DONE)
