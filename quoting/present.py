"""HTML for the quoting desk. Shared by the demo server and the signed-in page."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from quoting.demo.scenarios import SCENARIO_LABELS, SCENARIO_ORDER


def _e(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def _value(form, key: str, default: str = "") -> str:
    if not form:
        return default
    if hasattr(form, "getlist"):
        found = form.getlist(key)
        raw = found[-1] if found else default
    else:
        raw = form.get(key, default)
        if isinstance(raw, (list, tuple)):
            raw = raw[-1] if raw else default
    if raw is None:
        return default
    return str(raw)


def _values(form, key: str) -> list[str]:
    if not form:
        return []
    if hasattr(form, "getlist"):
        return [str(item) for item in form.getlist(key) if str(item) != ""]
    raw = form.get(key, [])
    if isinstance(raw, str):
        return [raw] if raw else []
    return [str(item) for item in raw]


def _on(form, key: str) -> bool:
    return _value(form, key).lower() in {"1", "true", "yes", "on"}


def _money(amount: str) -> str:
    return f"${Decimal(amount):,.2f}"


def _invalid_names(result) -> set[str]:
    if result is None:
        return set()
    return {issue.field for issue in result.issues}


def _field(form, name, label, invalid, *, kind="text", hint=""):
    classes = "field is-invalid" if name in invalid else "field"
    hint_html = f'<small>{_e(hint)}</small>' if hint else ""
    return (
        f'<label class="{classes}"><span>{_e(label)}</span>'
        f'<input name="{_e(name)}" type="{kind}" value="{_e(_value(form, name))}">'
        f"{hint_html}</label>"
    )


def _select(form, name, label, invalid, options):
    current = _value(form, name)
    classes = "field is-invalid" if name in invalid else "field"
    choices = ['<option value="">Choose</option>']
    for value, text in options:
        selected = " selected" if current == value else ""
        choices.append(f'<option value="{_e(value)}"{selected}>{_e(text)}</option>')
    return (
        f'<label class="{classes}"><span>{_e(label)}</span>'
        f'<select name="{_e(name)}">{"".join(choices)}</select></label>'
    )


def _check(form, name, label):
    checked = " checked" if _on(form, name) else ""
    return (
        f'<label class="check"><input type="checkbox" name="{_e(name)}" value="yes"{checked}>'
        f"<span>{_e(label)}</span></label>"
    )


def _driver_block(form, index, invalid) -> str:
    prefix = f"driver_{index}"
    filled = any(
        _value(form, f"{prefix}_{field}")
        for field in (
            "first_name",
            "last_name",
            "date_of_birth",
            "license_number",
            "license_state",
            "years_licensed",
            "accidents",
            "violations",
        )
    )
    hidden = "" if index == 1 or filled else " hidden"
    relationship = (
        ("named_insured", "Named insured"),
        ("spouse", "Spouse"),
        ("child", "Child"),
        ("parent", "Parent"),
        ("other", "Other"),
    )
    body = "".join(
        (
            _field(form, f"{prefix}_first_name", "First name", invalid),
            _field(form, f"{prefix}_last_name", "Last name", invalid),
            _field(form, f"{prefix}_date_of_birth", "Date of birth", invalid, kind="date"),
            _field(form, f"{prefix}_license_number", "License number", invalid),
            _field(form, f"{prefix}_license_state", "License state", invalid),
            _select(form, f"{prefix}_relationship", "Relationship", invalid, relationship),
            _field(form, f"{prefix}_years_licensed", "Years licensed", invalid),
            _field(form, f"{prefix}_accidents", "Accidents, 3 years", invalid),
            _field(form, f"{prefix}_violations", "Violations, 3 years", invalid),
            _field(form, f"{prefix}_license_state_reason", "Why the license is not New York", invalid),
        )
    )
    return (
        f'<fieldset class="block" data-driver{hidden}>'
        f"<legend>Driver {index}</legend>"
        f'<div class="grid">{body}</div>'
        f'<div class="checks">{_check(form, f"{prefix}_mvr_required", "MVR still needed for this driver")}</div>'
        f"</fieldset>"
    )


def _vehicle_block(form, index, invalid) -> str:
    prefix = f"vehicle_{index}"
    filled = any(
        _value(form, f"{prefix}_{field}")
        for field in ("year", "make", "model", "vin", "garaging_zip")
    )
    hidden = "" if index == 1 or filled else " hidden"
    body = "".join(
        (
            _field(form, f"{prefix}_year", "Year", invalid),
            _field(form, f"{prefix}_make", "Make", invalid),
            _field(form, f"{prefix}_model", "Model", invalid),
            _field(form, f"{prefix}_vin", "VIN", invalid),
            _select(
                form,
                f"{prefix}_usage",
                "Use",
                invalid,
                (("pleasure", "Pleasure"), ("commute", "Commute"), ("business", "Business")),
            ),
            _select(
                form,
                f"{prefix}_ownership",
                "Ownership",
                invalid,
                (("owned", "Owned"), ("financed", "Financed"), ("leased", "Leased")),
            ),
            _field(form, f"{prefix}_lienholder", "Lienholder", invalid),
            _field(form, f"{prefix}_garaging_zip", "Garaging ZIP", invalid),
        )
    )
    return (
        f'<fieldset class="block" data-vehicle{hidden}>'
        f"<legend>Vehicle {index}</legend><div class=\"grid\">{body}</div></fieldset>"
    )


def _issues(result) -> str:
    if result is None or not result.issues:
        return ""
    items = "".join(f"<li>{_e(issue.message)}</li>" for issue in result.issues)
    return (
        '<section class="notice notice-stop">'
        "<h2>Intake is incomplete</h2>"
        "<p>Nothing was sent to a carrier.</p>"
        f"<ul>{items}</ul></section>"
    )


def _results(result) -> str:
    if result is None:
        return (
            '<section class="notice">'
            "<h2>No quote run yet</h2>"
            "<p>Review the applicant, then run fixture quotes. A carrier that needs a person stops, "
            "and the card names what is missing.</p></section>"
        )
    if result.status != "completed":
        return ""
    quoted = [item for item in result.results if item.status == "quoted"]
    lowest = None
    if quoted:
        lowest = min(item.offer.term_premium for item in quoted if item.offer is not None)
    cards = []
    for item in result.results:
        cards.append(_card(item, lowest=lowest))
    summary = _summary(result)
    return f'<div class="result-stack">{summary}{"".join(cards)}</div>'


def _summary(result) -> str:
    quoted = sum(1 for item in result.results if item.status == "quoted")
    stopped = sum(1 for item in result.results if item.status == "blocked")
    needs = sum(1 for item in result.results if item.status == "needs_credentials")
    bits = []
    if quoted:
        bits.append(f"{quoted} fixture quote" if quoted == 1 and result.mode == "demo" else f"{quoted} quote")
        if result.mode == "demo" and quoted != 1:
            bits[-1] = f"{quoted} fixture quotes"
    if stopped:
        bits.append(f"{stopped} stopped")
    if needs:
        bits.append(f"{needs} need a portal login")
    label = " · ".join(bits) if bits else "No carriers ran"
    mode = "Fixture demo" if result.mode == "demo" else "Portal readiness"
    return f'<p class="summary"><span>{_e(mode)}</span>{_e(label)}</p>'


def _card(item, *, lowest) -> str:
    if item.status == "quoted" and item.offer is not None:
        badge = "Quoted"
        badge_class = "pill pill-quoted"
        premium = _money(item.offer.to_dict()["term_premium"])
        lowest_note = ""
        if lowest is not None and item.offer.term_premium == lowest and item.offer.illustrative:
            lowest_note = '<p class="lowest">Lowest fixture</p>'
        rows = "".join(
            f"<li><span>{_e(label)}</span><strong>{_e(value)}</strong></li>"
            for label, value in item.offer.coverages
        )
        body = (
            f'<p class="premium">{_e(premium)}</p>'
            f'<p class="term">{item.offer.term_months}-month term · {_e(item.offer.quote_number)}</p>'
            f"{lowest_note}"
            f'<ul class="coverages">{rows}</ul>'
            f'<p class="note">{_e(item.offer.note)}</p>'
        )
    else:
        blocker = item.blocker
        badge = "Needs portal login" if item.status == "needs_credentials" else "Stopped"
        badge_class = "pill pill-need" if item.status == "needs_credentials" else "pill pill-stop"
        missing = ""
        if blocker is not None:
            origin = ""
            if blocker.origin == "demo":
                origin = '<p class="origin">Demo rule</p>'
            items = "".join(f"<li>{_e(line)}</li>" for line in blocker.missing)
            missing = (
                f"{origin}<h3>{_e(blocker.title)}</h3>"
                f'<p class="note">{_e(blocker.detail)}</p>'
                f'<p class="missing-label">What is missing</p><ul class="missing">{items}</ul>'
            )
        body = missing
    return (
        f'<article class="card">'
        f'<header><h2>{_e(item.carrier_name)}</h2><span class="{badge_class}">{badge}</span></header>'
        f"{body}"
        f'<p class="portal"><a href="{_e(item.portal_url)}" rel="noopener noreferrer">Open the agent portal</a></p>'
        f"</article>"
    )


def _secrets(rows) -> str:
    if not rows:
        return ""
    items = []
    for row in rows:
        state = "set" if row["present"] else "not set"
        cls = "secret is-set" if row["present"] else "secret"
        items.append(
            f'<li class="{cls}"><span class="secret-top"><span>{_e(row["carrier_name"])}</span>'
            f"<em>{state}</em></span><code>{_e(row['name'])}</code></li>"
        )
    return (
        '<section class="secrets"><h2>Portal environment variables</h2>'
        "<p>The desk reads whether each name is set. Values stay in the server environment.</p>"
        f'<ul>{"".join(items)}</ul></section>'
    )


def render_desk(
    *,
    form,
    result,
    secrets,
    csrf_token: str | None = None,
    banner: str,
    back_url: str | None = None,
    back_label: str = "Back",
    saved_job_id: int | None = None,
    scenario: str | None = None,
    lead_id: str | None = None,
) -> str:
    invalid = _invalid_names(result)
    token = (
        f'<input type="hidden" name="csrfmiddlewaretoken" value="{_e(csrf_token)}">'
        if csrf_token
        else ""
    )
    lead_input = f'<input type="hidden" name="lead" value="{_e(lead_id)}">' if lead_id else ""
    back = f'<a class="back" href="{_e(back_url)}">{_e(back_label)}</a>' if back_url else ""
    saved = f'<p class="saved">Saved as quote job {_e(saved_job_id)}.</p>' if saved_job_id else ""
    scenario_links = []
    lead_query = f"&lead={_e(lead_id)}" if lead_id else ""
    for key in SCENARIO_ORDER:
        current = " is-current" if key == scenario else ""
        scenario_links.append(
            f'<a class="scenario{current}" href="?scenario={_e(key)}{lead_query}">{_e(SCENARIO_LABELS[key])}</a>'
        )
    selected = set(_values(form, "carriers"))
    carrier_boxes = []
    for key, label in (
        ("progressive", "Progressive"),
        ("national_general", "National General"),
        ("nyaip", "NY Automobile Insurance Plan"),
    ):
        checked = " checked" if key in selected else ""
        carrier_boxes.append(
            f'<label class="check"><input type="checkbox" name="carriers" value="{key}"{checked}>'
            f"<span>{label}</span></label>"
        )
    bi = (("25/50", "25/50"), ("50/100", "50/100"), ("100/300", "100/300"), ("250/500", "250/500"))
    pd = (("10", "10"), ("25", "25"), ("50", "50"), ("100", "100"))
    pip = (("50000", "50,000 basic"), ("100000", "100,000"))
    deductibles = (("none", "None"), ("100", "100"), ("250", "250"), ("500", "500"), ("1000", "1000"))
    drivers = "".join(_driver_block(form, index, invalid) for index in range(1, 7))
    vehicles = "".join(_vehicle_block(form, index, invalid) for index in range(1, 5))
    page = _PAGE.format(
        back=back,
        banner=_e(banner),
        saved=saved,
        scenarios="".join(scenario_links),
        token=token,
        lead_input=lead_input,
        issues=_issues(result),
        results=_results(result),
        secrets=_secrets(secrets),
        insured_fields="".join(
            (
                _field(form, "insured_first_name", "First name", invalid),
                _field(form, "insured_last_name", "Last name", invalid),
                _field(form, "insured_date_of_birth", "Date of birth", invalid, kind="date"),
                _field(form, "insured_phone", "Phone", invalid),
                _field(form, "insured_email", "Email", invalid),
                _field(form, "effective_date", "Effective date", invalid, kind="date"),
                _field(form, "insured_street", "Street", invalid),
                _field(form, "insured_city", "City", invalid),
                _field(form, "insured_state", "State", invalid),
                _field(form, "insured_zip", "ZIP", invalid),
            )
        ),
        drivers=drivers,
        vehicles=vehicles,
        coverage="".join(
            (
                _select(form, "coverage_bi", "Bodily injury", invalid, bi),
                _select(form, "coverage_pd", "Property damage", invalid, pd),
                _select(form, "coverage_pip", "PIP", invalid, pip),
                _select(form, "coverage_um", "Uninsured motorist", invalid, bi),
                _select(form, "coverage_comp", "Comprehensive deductible", invalid, deductibles),
                _select(form, "coverage_coll", "Collision deductible", invalid, deductibles),
                _select(form, "coverage_term", "Term", invalid, (("6", "6 months"), ("12", "12 months"))),
            )
        ),
        prior="".join(
            (
                _check(form, "currently_insured", "Currently insured"),
                _field(form, "prior_carrier", "Current carrier", invalid),
                _field(form, "prior_expiration", "Current expiration", invalid, kind="date"),
                _field(form, "prior_lapse_reason", "Reason there is no current policy", invalid),
                _check(form, "mvr_pending", "MVR still pending for this quote"),
                _check(form, "voluntary_market_declined", "A voluntary carrier already declined this applicant"),
                _field(form, "declination_carrier", "Carrier that declined", invalid),
            )
        ),
        carriers="".join(carrier_boxes),
    )
    return page


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect fill='%231b3358' width='16' height='16' rx='3'/%3E%3C/svg%3E">
<title>NY personal auto quoting</title>
<style>
  :root {{
    --ink: #1c1915;
    --muted: #5e564c;
    --paper: #f3efe4;
    --card: #fffdf8;
    --navy: #1b3358;
    --navy-2: #2c4c7c;
    --line: #e3d9c8;
    --quoted: #1d6b45;
    --quoted-bg: #e7f4ec;
    --stop: #8a4b08;
    --stop-bg: #f8ecd9;
    --need: #33475b;
    --need-bg: #e7eef3;
    --danger: #8d2f2f;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    color: var(--ink);
    background: var(--paper);
    font: 16px/1.45 "Avenir Next", "Segoe UI", sans-serif;
  }}
  header.top {{
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: end;
    padding: 1.25rem 1.5rem 1.1rem;
    background: var(--navy);
    color: #f7f3ea;
  }}
  .brand {{ font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; font-size: 0.78rem; }}
  header.top h1 {{ margin: 0.15rem 0 0; font-family: Palatino, "Iowan Old Style", Georgia, serif; font-size: 2rem; font-weight: 600; }}
  .eyebrow {{ margin: 0; color: #d5deea; font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; }}
  .back {{ color: #f7f3ea; }}
  .banner, .saved {{ margin: 0; }}
  .banner {{
    padding: 0.85rem 1.5rem;
    background: #efe6d4;
    color: var(--ink);
    border-bottom: 1px solid var(--line);
  }}
  .saved {{ padding: 0.7rem 1.5rem 0; font-weight: 650; }}
  .layout {{
    display: grid;
    grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
    gap: 1rem;
    padding: 1rem 1.5rem 2rem;
    align-items: start;
  }}
  form, .results {{ min-width: 0; }}
  .panel {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 1rem 1rem 1.1rem;
    margin-bottom: 0.8rem;
  }}
  .panel h2, .card h2, .notice h2, .secrets h2 {{
    margin: 0;
    font-family: Palatino, "Iowan Old Style", Georgia, serif;
    font-size: 1.35rem;
    font-weight: 600;
  }}
  .scenarios {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.75rem; }}
  .scenario, button, .portal a {{
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    text-decoration: none;
  }}
  .scenario {{
    padding: 0.35rem 0.7rem;
    border: 1px solid var(--line);
    color: var(--navy);
    background: #fff;
    font-size: 0.86rem;
  }}
  .scenario.is-current {{ background: var(--navy); color: white; border-color: var(--navy); }}
  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.7rem; }}
  .field {{ display: grid; gap: 0.25rem; }}
  .field span, .missing-label {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }}
  input, select {{
    width: 100%;
    border: 1px solid #d4cbbd;
    background: #fff;
    color: var(--ink);
    border-radius: 10px;
    padding: 0.55rem 0.65rem;
    font: inherit;
  }}
  .is-invalid input, .is-invalid select {{ border-color: var(--danger); background: #fff6f4; }}
  .block {{ border: 1px solid var(--line); border-radius: 14px; margin: 0.7rem 0 0; padding: 0.8rem; }}
  .block legend {{ padding: 0 0.3rem; font-weight: 700; }}
  .checks, .carrier-picks {{ display: flex; flex-wrap: wrap; gap: 0.6rem 1rem; margin-top: 0.7rem; }}
  .check {{ display: flex; gap: 0.45rem; align-items: center; font-weight: 600; }}
  .check input {{ width: auto; }}
  .actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.9rem; }}
  button {{
    border: 0;
    background: var(--navy);
    color: white;
    padding: 0.7rem 1rem;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }}
  button.secondary {{ background: transparent; color: var(--navy); border: 1px solid var(--navy-2); }}
  button.linkish {{ background: transparent; color: var(--navy-2); padding: 0.4rem 0; border-radius: 0; }}
  .results {{ position: sticky; top: 0.8rem; }}
  .notice, .card, .secrets {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 1rem;
    margin-bottom: 0.8rem;
  }}
  .notice-stop {{ border-color: #e7c7a4; background: #fff8ef; }}
  .notice p, .note, .secrets p {{ color: var(--muted); }}
  .summary {{ display: flex; justify-content: space-between; gap: 0.5rem; margin: 0 0 0.8rem; font-weight: 700; }}
  .summary span {{ color: var(--navy); }}
  .card header {{ display: flex; justify-content: space-between; gap: 0.6rem; align-items: start; }}
  .pill {{ border-radius: 999px; padding: 0.2rem 0.55rem; font-size: 0.75rem; font-weight: 800; white-space: nowrap; }}
  .pill-quoted {{ background: var(--quoted-bg); color: var(--quoted); }}
  .pill-stop {{ background: var(--stop-bg); color: var(--stop); }}
  .pill-need {{ background: var(--need-bg); color: var(--need); }}
  .premium {{ margin: 0.35rem 0 0; font-family: Palatino, Georgia, serif; font-size: 2rem; }}
  .term, .lowest {{ margin: 0.15rem 0 0; }}
  .lowest {{ color: var(--quoted); font-weight: 800; font-size: 0.82rem; letter-spacing: 0.04em; text-transform: uppercase; }}
  .coverages, .missing, .secrets ul {{ list-style: none; padding: 0; margin: 0.7rem 0 0; }}
  .coverages li {{ display: flex; justify-content: space-between; gap: 0.8rem; padding: 0.35rem 0; border-top: 1px solid var(--line); }}
  .secrets li {{ display: flex; flex-direction: column; align-items: stretch; gap: 0.15rem; min-width: 0; padding: 0.45rem 0; border-top: 1px solid var(--line); }}
  .secret-top {{ display: flex; justify-content: space-between; gap: 0.6rem; min-width: 0; }}
  .secret-top span {{ min-width: 0; }}
  .missing li {{ margin: 0.25rem 0; padding-left: 0.9rem; position: relative; }}
  .missing li::before {{ content: ""; width: 0.4rem; height: 0.4rem; border-radius: 50%; background: var(--stop); position: absolute; left: 0; top: 0.45rem; }}
  .origin {{ margin: 0.55rem 0 0; font-size: 0.75rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: var(--stop); }}
  .portal {{ margin: 0.8rem 0 0; }}
  .portal a {{ color: var(--navy); font-weight: 700; }}
  .secrets code {{ font-size: 0.78rem; overflow-wrap: anywhere; }}
  .secrets em {{ font-style: normal; font-weight: 700; white-space: nowrap; }}
  .secret.is-set em {{ color: var(--quoted); }}
  @media (max-width: 960px) {{
    .layout {{ grid-template-columns: 1fr; padding: 0.8rem; }}
    .results {{ position: static; order: -1; }}
    header.top {{ align-items: start; flex-direction: column; }}
    header.top h1 {{ font-size: 1.7rem; }}
  }}
  @media (max-width: 640px) {{
    .grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<header class="top">
  <div>
    <p class="brand">RegiManager</p>
    <p class="eyebrow">New York personal auto</p>
    <h1>Quoting desk</h1>
  </div>
  {back}
</header>
<p class="banner">{banner}</p>
{saved}
<div class="layout">
  <form method="post" action="">
    {token}
    {lead_input}
    <input type="hidden" name="carriers_submitted" value="1">
    <section class="panel">
      <h2>Sample paths</h2>
      <div class="scenarios">{scenarios}</div>
    </section>
    <section class="panel">
      <h2>Named insured</h2>
      <div class="grid">{insured_fields}</div>
    </section>
    <section class="panel">
      <h2>Drivers</h2>
      {drivers}
      <button class="linkish" type="button" data-add="driver">Add a driver</button>
    </section>
    <section class="panel">
      <h2>Vehicles</h2>
      {vehicles}
      <button class="linkish" type="button" data-add="vehicle">Add a vehicle</button>
    </section>
    <section class="panel">
      <h2>Coverage</h2>
      <div class="grid">{coverage}</div>
    </section>
    <section class="panel">
      <h2>Prior insurance and plan eligibility</h2>
      <div class="grid">{prior}</div>
    </section>
    <section class="panel">
      <h2>Carriers</h2>
      <div class="carrier-picks">{carriers}</div>
      <div class="actions">
        <button type="submit" name="run" value="demo">Run fixture quotes</button>
        <button class="secondary" type="submit" name="run" value="live">Check portal readiness</button>
      </div>
    </section>
  </form>
  <aside class="results">
    {issues}
    {results}
    {secrets}
  </aside>
</div>
<script>
  document.querySelectorAll("[data-add]").forEach(function (button) {{
    button.addEventListener("click", function () {{
      var kind = button.getAttribute("data-add");
      var blocks = document.querySelectorAll("[data-" + kind + "]");
      for (var i = 0; i < blocks.length; i += 1) {{
        if (blocks[i].hidden) {{
          blocks[i].hidden = false;
          var input = blocks[i].querySelector("input, select");
          if (input) input.focus();
          return;
        }}
      }}
    }});
  }});
</script>
</body>
</html>
"""

