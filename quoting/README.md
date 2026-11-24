# NY personal auto quoting

v1 quotes **personal auto in New York** for the agent's own clients. The first carriers are Progressive (ForAgentsOnly), National General (NatGenAgency), and the New York Automobile Insurance Plan (PASS, Assigned Risk). Another carrier is a new adapter registered in `quoting/carriers/registry.py`. Another line is a validator plus carriers that opt into it.

The desk takes the named insured, drivers, vehicles, and coverages, then runs a quote job. A carrier that needs an MVR, a referral, a special case, or a portal step that is not finished **stops**. The card names what is missing. No premium is filled in for that carrier.

## Run the demo

From the repo root, with the project dependencies installed:

```bash
python -m quoting --check
python -m quoting
```

`--check` prints the sample paths and exits. `python -m quoting` serves the desk at [http://127.0.0.1:8765](http://127.0.0.1:8765) on this machine only.

The page loads a sample applicant, Maya Hassan. Use the sample paths (clean voluntary, MVR, referral, Assigned Risk, no prior reason), edit the form, and choose **Run fixture quotes**. Premiums are illustrative fixtures, not carrier rates. **Check portal readiness** reports which environment variables are set. It does not log in.

The same desk is at `/quoting/` after you sign in to RegiManager, and from an auto quote in the pipeline. That path saves the job. The demo server does not.

## Portal logins

The app reads these names from the environment and only keeps whether each one is set. Put the values in the server environment. Do not commit them, and do not paste them into chat.

- `PROGRESSIVE_AGENT_PORTAL_USERNAME`
- `PROGRESSIVE_AGENT_PORTAL_PASSWORD`
- `NATIONAL_GENERAL_AGENT_PORTAL_USERNAME`
- `NATIONAL_GENERAL_AGENT_PORTAL_PASSWORD`
- `NYAIP_AGENT_PORTAL_USERNAME`
- `NYAIP_AGENT_PORTAL_PASSWORD`

They are listed empty in `.env.example`. Live mode does not submit a portal quote from this build. When the variables are set, the carrier stops and asks for an agent-completed portal session. MFA and bot checks are not bypassed. A future session driver has to stop when the portal shows either one.

Demo referral rules are labeled **Demo rule** on the card. Live mode does not use those rules in place of the portal.
