# RBAC in DA Services

Deny by default, enforced in the backend on every call. A Frappe **Role** says which
actions exist for a user; a **DA RBAC Assignment** says over which Region, Woreda or DA
they may act. Both are required (HLD 3: "RBAC is necessary but not sufficient").

## Roles (FSD Appendix B)

| Role | Scope | Desk |
|---|---|---|
| Development Agent | own DA-ID | no (mobile app and API) |
| Supervisor | own Woreda | yes |
| Executive | own Region, read-only | yes |
| OAN Administrator | all | yes |
| Communications Officer | broadcast domain, no DA identity | yes |

"Woreda Officer" and "Senior DA" are titles, not roles: they get approval authority only
through a Supervisor assignment (HLD 3, 10.1). Roles are seeded by
`setup/install.py` on install and on every migrate.

## Assignment model

`DA RBAC Assignment`: `user`, `role`, `active`, `da_id`, `region_scope`, `woreda_scope`,
`effective_from`, `effective_to`, `assigned_by`, `notes`.

Validation: Supervisor needs a Woreda; Executive needs a Region; Development Agent needs
a DA-ID; a Woreda needs its Region; `effective_to >= effective_from`. Saving an active
grant adds the role to the User; revocation deactivates the row and closes the window
but never deletes it.

Region / Woreda are stored as administrative codes. Zone will be added when the field
list is final.

## Scope rule (`utils/permissions.py`)

`get_scope_context(user)` reads the user's active, in-window assignments once per
request. `require_roles(...)` and `require_da_access(da_id, region, woreda)` apply:

1. Unrestricted (OAN Administrator, System Manager, Administrator): always.
2. Supervisor / Executive: only if the DA's Region/Woreda, **as returned by the
   registry**, is inside their scope. A Woreda grant covers that Woreda; a Region-only
   grant covers every Woreda in it.
3. Development Agent: only their own DA-ID.
4. Anyone else, including Communications Officer: denied.

Caller-supplied Region/Woreda values are never trusted for the check.

## Authentication

Login, refresh, logout and password reset come from the shared `oan_auth_service` app
(same as the Grievance service). Its JWT middleware protects two namespaces for us:

- `/api/v1/da/*` (REST routes declared with `@route` in `api/router.py`)
- `/api/method/da_services.*` (the RPC form of the same functions)

On each request the token's `sub` becomes the session user; our scope context is then
built from that user's assignments. `GET /api/v1/auth/me` (auth app) includes our profile
under `data.profiles.da_services`; `GET /api/v1/da/me` returns the full profile with the
DA record and the permitted menu.

Fayda sign-in and central OAN IAM are open decisions; the auth layer is isolated so
either can replace the interim login without touching the scope rule.

## Frappe permission hooks

`permissions.py` registers `permission_query_conditions` and `has_permission` for the
app's doctypes so list views, reports and `/api/resource` obey the same rule as the API.
Every new doctype must register both before it is exposed.

## Testing (FSD Appendix D)

Roles are verified by what they **cannot** do. `tests/test_rbac.py` and
`tests/test_api_auth.py` cover: Supervisor outside own Woreda, Executive outside own
Region, DA reading another DA, Communications Officer touching DA identity, expired
grant, Guest, token without any assignment. The full negative matrix per role is a
pending subtask.

## Open points

- Zone level in scope (Shikha's field list).
- Role names vs the approved OAN RBAC model.
- Mapping of these roles to OpenG2P groups and Woreda scoping in registry views (with Yash).
- User provisioning: Registry approval → Services user + assignment.
- Audit events for denials and assignment changes (pending subtask).
