# Authorization map

Enforcement is **`OrganizationMembership` flags and roles**, not Django `user.has_perm` and not django-guardian.

## Space gate

1. Active membership (or superuser).
2. `can_view_spaces`.
3. Insurance space in `accessible_spaces`.

Owners are **not** exempt on the web UI. Owner companion API `spaces_for_membership()` currently returns all spaces for role=owner — do not copy that inconsistency into RegiConnect; always filter by membership + org.

## Insurance work

| Action | Rule today |
|---|---|
| Policy detail / DEC | owner or `can_deal_with_insurance` |
| Quote pipeline view/create | superuser, owner/manager, or `can_deal_with_insurance` |
| Auto-distribution pool | `can_deal_with_insurance` **and** role `insurance_agent` |
| Manage distribution / delete leads | owner/manager |
| Companies / Finance / commission fields / daily-payment clear | owner/superuser or `can_view_banking` |
| E-sign | owner or (spaces + insurance accessible) |

`can_manage_insurance_pipeline` was removed (migration 0106).

## Role packs (`core/role_permissions.py`)

Assigning a role writes a boolean pack. Owners typically bypass via `is_org_owner`. Insurance agent pack sets `can_deal_with_insurance` and `can_view_spaces`; banking false.

## Tenant isolation

Every query must include `organization=` (or `organization__in=` for the user's orgs). Session `active_org_id` narrows the dashboard. APIs use `X-Organization-Id` if the user belongs to that org. There is **no** automatic queryset middleware — forgetting the filter is a cross-tenant bug.

Vehicles: always join `client__organization`.

## RegiConnect flags (to add)

Keep the same pattern (two flags, not dotted permission strings):

- `can_view_regiconnect` — Markets/Connectivity/Regi Rater read.
- `can_manage_regiconnect` — appointments, connections, submit/retry, certification (owners/managers).

Never expose credential material to any of these flags. Secrets stay in the secret backend.
