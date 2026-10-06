# DA role screens → APIs, doctypes and data sources

Source: DA UI prototype (`da-registry-development.oanstaging.com`, mock data, 6 Oct 2026),
screens seen after a Development Agent logs in. Companion to `data-model.md`; doctype names
and field names follow it. All routes are under `/api/v1/da-services/` and use the shared
response envelope. Every write that a device can capture offline carries `client_op_id`.

Legend for **Source**: `ours` = DA Services doctype; `Registry` = DA Registry (OpenG2P);
`Farmer Registry`, `Grievance`, `ODK`, `Land Registry`, `Credit` = external systems;
`derived` = computed at read time, not stored; `device` = lives on the device only.

## 0. Shell (every screen)

| Element | API | Source |
|---|---|---|
| User menu: name, role, avatar; sidebar sections | `GET /me` (exists) | ours + Registry |
| Footer "Own record · Bako Tibe" | `GET /me` → `agent.kebele` | Registry |
| Notification bell + unread dot | `GET /notifications?unread=1&limit=20`, `POST /notifications/{id}/read` | ours: DA Notification |
| Language switch | client only; `Accept-Language` header on every call | – |
| "Search portal..." | `GET /search?q=` (farmers, visits, grievances, KB articles) | ours + Farmer Registry projection; **phase 2** |

## 1. Dashboard (`/dashboard`)

| Element | API | Source |
|---|---|---|
| Date range (7 / 30 / 90 days, quarter, year, custom) | `from`, `to` query params on summary | – |
| Tile: Farm visits "4 of 6 planned" + progress bar | `GET /dashboard/summary?from&to` → `visits.completed`, `visits.planned` | ours: DA Visit |
| Tile: Tasks "4 open · 3 done", chips 1 URGENT, 2 DUE TODAY | same → `tasks.open`, `tasks.done`, `tasks.urgent`, `tasks.due_today` | ours: DA Task |
| Tile: Sync status "All data synced · 5 min ago" | same → `sync.server_pending`, `sync.last_received_at`; device merges its own queue count | ours: DA Device Sync Operation + device |
| Today's Plan (visits + tasks merged, time-sorted, chips UPCOMING / DUE TODAY) | `GET /dashboard/today?date=` | ours: DA Visit + DA Task (derived merge) |
| "View calendar" | link to Visit Planner | – |
| Quick actions: Register Farmer, Submit Crop Report, Start Farm Visit, Sync Queue | links only | – |

`GET /dashboard/summary` response:

```json
{
  "range": {"from": "2026-09-06", "to": "2026-10-06"},
  "visits": {"completed": 4, "planned": 6},
  "tasks": {"open": 4, "done": 3, "urgent": 1, "due_today": 2},
  "sync": {"server_pending": 0, "failed": 0, "conflicts": 0, "last_received_at": "2026-10-06T15:59:00Z"}
}
```

`GET /dashboard/today` response (one list, two item kinds):

```json
{
  "date": "2026-10-06",
  "items": [
    {"kind": "visit", "id": "DA-VIS-2026-0000012", "time": "08:30", "title": "Farm visit: Lelise Gudeta, Bako Tibe",
     "subtitle": "Crop inspection", "status": "Upcoming", "farmer_id": "FR-88466"},
    {"kind": "task", "id": "DA-TSK-2026-0000031", "time": "13:00", "title": "Submit weekly crop report",
     "subtitle": "National agriculture statistics deadline", "status": "Due today", "priority": "Normal"}
  ]
}
```

Status chip rules (derived): visit `Upcoming` when `physical_status in (Planned, Confirmed)` and
`scheduled_at >= now`; `Overdue` when past and not complete; task `Due today` when `due_at` is today
and `status = Open`; `Urgent` from `priority`.

## 2. Register Farmer (`/farmers/new`, 5 steps, Save Draft, Next Step)

The farmer master is the **Farmer Registry**. DA Services never stores a second farmer master;
it submits, links the farmer to the DA and keeps a read projection (data-model 5.1, 5.2).

| Element | API | Source |
|---|---|---|
| Step 1 fields: photo, first name, last name, mobile, email, DOB, gender, ID type, ID number, language | `POST /farmers` (final submit, step 5) → Farmer Registry create → `DA Farmer Link` (mode Automatic) → projection refresh | Farmer Registry + ours |
| Dropdowns: ID type, gender, language | `GET /master/reference-values?type=id_type\|gender\|language` | ours: DA Reference Value |
| Step 2 Location and kebele | `GET /master/regions`, `/master/zones?region=`, `/master/woredas?zone=`, `/master/kebeles?woreda=` | ours: DA Administrative Area |
| Photo / documents | `POST /files` (multipart; returns `file_url`, `content_hash`) | ours (Frappe File) |
| Save Draft | **device** (sync queue). Server receives only the final submit. No server-side draft doctype | device |
| Validation per step | client; server validates the whole payload on submit and returns field errors in the envelope | – |
| Duplicate check (phone / ID number) | `GET /farmers/check-duplicate?phone=&id_number=` → Farmer Registry search | Farmer Registry |

Steps 2–4 fields (location, ID and documents, specialization and qualification) are not in the
screenshots; the Farmer Registry contract decides the payload. **Open:** the prototype uses
First / Last Name and a Gregorian DOB; Shikha's field list uses Name / Father / Grandfather and
Ethiopian-calendar birth month/year. The API should follow the Farmer Registry schema, not the mock.

## 3. Plan a visit (modal on Visit Planner / Visit Outcome)

| Element | API | Source |
|---|---|---|
| Farmer search (name, phone, kebele) + chips "Registered", "Input voucher redeemed this season" | `GET /farmers?q=&limit=10` over own farmers; `flags[]` from projection + beneficiary data | ours: DA Farmer Reference; voucher flag external (**contract pending**) |
| Farmer card: `FR-88466 · Bako Tibe · Teff 1.2 ha · last visit 34 days ago` | same list item: `farmer_id`, `kebele`, `primary_crop`, `area_ha`, `last_visit_at` (derived from DA Visit) | ours |
| Visit type: Crop Survey / Livestock Survey / Services / Follow-up | `visit_type` enum (data-model 5.3; Advisory also exists) | ours |
| Purpose, date, time, duration, priority | `POST /visits` | ours: DA Visit |
| Location "auto-filled from the farmer's registered parcel" | server fills `location_lat/lng` from Farmer Registry parcel if client omits | Farmer Registry |
| Priority "High — overdue by 4 days" | `priority` stored; "overdue by N days" derived from the task that triggered it | derived |
| Save as draft | device | device |
| "Planned offline — queued on this device" | `POST /visits` is idempotent on `client_op_id`; the device replays it through `POST /sync/operations` | ours |
| "Plan a field visit and notify the farmer" | `notify_farmer_sms: true` → SMS job | ours + SMS gateway |

`POST /visits` body:

```json
{
  "client_op_id": "7f3c...", "farmer_id": "FR-88466", "visit_type": "Crop Survey",
  "purpose": "Planning-round crop survey: record plot boundary and crop split",
  "scheduled_at": "2026-08-25T09:00:00+03:00", "duration_min": 45,
  "priority": "High", "location": {"lat": 8.191, "lng": 37.05}, "notify_farmer_sms": true
}
```

## 4. Visit Planner (`/visits`)

| Element | API | Source |
|---|---|---|
| Week / month calendar, legend Scheduled / Completed / Overdue, prev/next | `GET /visits?from&to&view=week` → items with `scheduled_at`, `farmer_name`, `kebele`, `status` | ours: DA Visit; `Overdue` derived |
| "Log visit outcome" | link to `/visits/{id}/outcome` | – |
| Priority list: farmers with critical issues (Armyworm infestation, Soil salinity test, Irrigation audit, Fertilizer delivery delay) + flag colour | `GET /farmers/priority?limit=10` → `farmer_id`, `issue`, `severity`, `source` | **derived**: open DA Tasks of type Follow-up / Survey due, open grievances, advisories. **Open:** where do pest alerts come from (Agrilearn? ODK survey results?) |
| "Schedule" per row | opens Plan a visit prefilled → `POST /visits` | ours |
| Today's visits: planned arrival, Done, "Confirmed · prefers morning", "Tentative · reconfirm by SMS" | `GET /visits?date=today` → `farmer_confirmation` (Confirmed / Tentative / Declined / Unknown) + `confirmation_note` | ours: DA Visit (**fields to add**, see §9) |
| "Start visit · Abebe Kebede" | `POST /visits/{id}/start` (GPS fix: `lat`, `lng`, `accuracy_m`, `captured_at`) → `physical_status = In progress` | ours |
| "View locations" (map) | same list, `location_lat/lng` per item | ours |
| Info box: "the app does not assign or optimise routes" | no routing API, by design | – |

## 5. Visit Outcome and activity report (`/visits/{id}/outcome`)

| Element | API | Source |
|---|---|---|
| Header: farmer, kebele, date/time, Completed badge | `GET /visits/{id}` | ours |
| Visit purpose, farmer response, what was observed, advice given, inputs/actions logged, next action and date | `PATCH /visits/{id}/outcome` (Save draft, partial) · `POST /visits/{id}/submit` (final; sets `physical_status = Physical Visit Complete`, `completed_at`) | ours: DA Visit |
| Photos / evidence (geo-tagged) | `POST /visits/{id}/attachments` (multipart + `lat`, `lng`, `captured_at`, `content_hash`, `kind`) | ours: DA Visit Attachment |
| Next action "Follow-up visit · 12 Aug 2026" | on submit, server creates `DA Task` (type Follow-up, `due_at`) and, if `next_action_type = Follow-up visit`, a Planned `DA Visit` (`source = Planned`) | ours |
| "Voucher issue logged as grievance" (mock row) | submit may carry `raise_grievance: {...}` → Grievance adapter | Grievance |
| Activity report, week of 24–30 Jun: Visits completed 14/16, Farmers reached 128, Advisories issued 2, Issues raised 2, Follow-ups 6 | `GET /reports/activity?week=2026-W26` | derived from DA Visit, DA Task, DA Grievance Link |
| Submitted visit outcomes list (farmer, kebele, type, outcome summary, date) | same response → `outcomes[]` | ours |
| "Activity Log" | `GET /visits?status=Physical Visit Complete&from&to` | ours |
| "Export Report" (dropdown) | `GET /reports/activity/export?week=&format=pdf\|xlsx` | ours (server-rendered) |

Counting rule (HLD 9.4): a visit counts as completed only when `physical_status = Physical Visit
Complete` and any required ODK survey link is `Complete`. The tile must use this rule, not
"submitted".

**Open:** the mock shows "Jun 24, 2016" for a 2026 visit. Either a mock bug or an Ethiopian-calendar
display (2016 EC ≈ 2024 GC). The API returns ISO Gregorian dates; EC display is a client concern.
Confirm with the UI team.

## 6. Agent Assignment (`/assignments`, tabs My Farmers · Visits · Assignments)

| Element | API | Source |
|---|---|---|
| Tiles: My kebele "Bako 01 · Bako Tibe woreda", Linked farmers 248, Effective since 12 Mar 2019, Assigned by "Almaz Tesfaye · Woreda supervisor" | `GET /assignments/me` | Registry (kebele, woreda, effective date, supervisor) via DA Agent Reference + ours (`DA Farmer Link` count) |
| Table row: Agent, DA-ID `DA-OR-000341`, Woreda, Kebele + since, Farmers, Status Active / Assignment Effective, Assigned by, View | same, as a one-row list for a DA. For a Supervisor the same screen is `GET /assignments?woreda=&q=&status=` (own Woreda) | Registry + ours |
| Search "Agent, DA-ID, Woreda, Kebele", Advanced filters | query params `q`, `woreda`, `kebele`, `status`, `assignment_state` | – |
| View | `GET /agents/{da_id}` (exists) | Registry |

**Open:** the mock DA-ID is `DA-OR-000341` (region-coded). Yash's registry issues `DA-` + 10 digits.
Our mock uses `DA-000001`. One format must win before the data model freezes; the API treats
`da_id` as an opaque string either way.

## 7. Sync Queue (`/sync`)

The queue itself lives on the device (IndexedDB). The server side is the idempotent intake,
conflict detection and the retry of pushes to external systems (data-model 5.7, 8.1).

| Element | API | Source |
|---|---|---|
| Tiles: Awaiting sync 4, Conflicts 1, Failed 1 (auto-retry scheduled), Device storage 71% | awaiting + storage = **device**; conflicts/failed = `GET /sync/status` | device + ours |
| "Sync now" | `POST /sync/operations` (batch; each op: `client_op_id`, `entity_type`, `operation`, `payload`, `base_version`, `captured_at`, `device_id`, `payload_hash`) → per-op `Accepted` / `Rejected` / `Conflict` + `entity_name` | ours: DA Device Sync Operation |
| Large items (1.1 MB, 3 photos; 620 KB photo + voice note) | `POST /sync/attachments` (chunked, `content_hash`), referenced from the op payload | ours |
| Row: Farmer update · Conflict · "Record changed on the server after this edit was captured" · Needs you — resolve | server compares `base_version` with current; `GET /sync/conflicts`, `GET /sync/conflicts/{id}` (field diffs), `POST /sync/conflicts/{id}/resolve` (`Keep mine` / `Keep server` / `Merge` + `merged_payload`) | ours: DA Sync Conflict → Farmer Registry on resolve |
| Row: Grievance · Failed · "Grievance Service timeout, auto-retry scheduled" · Retry | `POST /sync/operations/{client_op_id}/retry` (server re-pushes to the external system) | ours → Grievance |
| Row: Plot boundary · "Held as Part-1 evidence until the Land Registry API is available" | op accepted and stored as evidence; `state = Accepted`, external push `Deferred` | ours (hold) → Land Registry (**no contract**) |
| Row: Credit application · Awaiting sync | op → Credit service adapter | Credit (**no contract yet**) |
| Rows: Visit outcome, Survey response, Certificate upload, Internal issue | ops applied to DA Visit / DA ODK Submission Link / DA Certificate / DA Internal Issue | ours (+ ODK for survey) |
| Device sync queue table: Item, Captured, Size, Status, Actions; filters | `GET /sync/operations?state=&entity_type=&from&to` (server's view, for audit and Supervisor support) | ours |

`POST /sync/operations` response per op:

```json
{"client_op_id": "7f3c...", "state": "Conflict", "entity_type": "DA Farmer Link", "entity_name": "FR-88466",
 "conflict_id": "DA-CNF-2026-0000004", "message": "Record changed on the server after this edit was captured"}
```

Entity type → owner system (decides where the server pushes after accepting):

| `entity_type` | Owner | Push |
|---|---|---|
| Farmer create / update | Farmer Registry | adapter, conflict on version |
| Visit plan / outcome / attachments | ours | none |
| Survey response | ours + ODK | ODK submission link |
| Plot boundary | Land Registry | deferred, held as evidence |
| Grievance | Grievance Service | adapter with retry |
| Certificate upload, Internal issue | ours | none |
| Credit application | Credit service | adapter, **contract pending** |

## 8. Consolidated endpoint list (this batch of screens)

| # | Method + path | Screen | Owner (proposed) |
|---|---|---|---|
| 1 | `GET /me` (exists) | shell | done |
| 2 | `GET /agents/{da_id}` (exists) | assignment | done |
| 3 | `GET /notifications`, `POST /notifications/{id}/read` | shell | Nikky |
| 4 | `GET /master/regions\|zones\|woredas\|kebeles`, `GET /master/reference-values` | register farmer, filters | Pushkar |
| 5 | `GET /dashboard/summary` | dashboard | Nikky |
| 6 | `GET /dashboard/today` | dashboard | Nikky |
| 7 | `GET /farmers`, `GET /farmers/{id}`, `GET /farmers/check-duplicate` | plan visit, my farmers | Nikky (after Farmer Registry contract) |
| 8 | `POST /farmers` | register farmer | Nikky (adapter) |
| 9 | `GET /farmers/priority` | planner | Nikky |
| 10 | `GET /visits`, `GET /visits/{id}` | planner, outcome | Nikky |
| 11 | `POST /visits` | plan visit | Nikky |
| 12 | `POST /visits/{id}/start` | planner | Nikky |
| 13 | `PATCH /visits/{id}/outcome`, `POST /visits/{id}/submit` | outcome | Nikky |
| 14 | `POST /visits/{id}/attachments` | outcome | Nikky |
| 15 | `GET /tasks`, `POST /tasks`, `POST /tasks/{id}/done` | dashboard tasks tile (list page not yet seen) | Nikky |
| 16 | `GET /reports/activity`, `GET /reports/activity/export` | outcome page | Nikky |
| 17 | `GET /assignments/me`, `GET /assignments` | assignment | Nikky |
| 18 | `POST /sync/operations`, `POST /sync/attachments`, `GET /sync/operations`, `GET /sync/status` | sync queue | Pushkar |
| 19 | `GET /sync/conflicts`, `GET /sync/conflicts/{id}`, `POST /sync/conflicts/{id}/resolve` | sync queue | Pushkar |
| 20 | `POST /sync/operations/{id}/retry` | sync queue | Pushkar |
| 21 | `POST /files` | uploads | Frappe built-in, wrap only |
| 22 | Grievance endpoints (6) | sidebar Grievances, sync queue row | Pushkar (ticket written) |

About 40 endpoints for these 7 screens. Sidebar items not yet seen: Beneficiaries, Grievances
(list page), My Teams, Internal Feedback, Knowledge Base, My Performance, Surveys.

## 9. Changes this implies for `data-model.md`

- **DA Visit**: add `farmer_response` (Small Text), `observed` (Text), `inputs_actions` (Small Text),
  `next_action_type` (Select: None / Follow-up visit / Task / Referral), `next_action_note`,
  `next_action_date` (Date), `farmer_confirmation` (Select: Unknown / Confirmed / Tentative /
  Declined), `confirmation_note` (Data), `outcome_submitted_at` (Datetime). `outcome` stays as the
  short summary shown in lists.
- **DA Task**: add `Visit prep` to `task_type`; `visit` link already covers the source visit.
- **DA Device Sync Operation**: add `base_version` (Data) and `external_push_state`
  (Select: Not needed / Pending / Deferred / Pushed / Failed) so "Held until Land Registry API"
  and "Grievance timeout" are separate from the intake state.
- **DA Farmer Reference**: add `last_visit_at` (maintained on visit submit) and `flags` (JSON) for
  chips such as voucher redeemed.
- New read models, no new doctypes: dashboard summary, today's plan, priority list, activity report.
- No server-side drafts for farmer registration or visit planning: drafts stay on the device.

## 10. Open questions from these screens

1. Farmer schema: First/Last + Gregorian DOB (mock) vs Name/Father/Grandfather + EC (Shikha). Follow the Farmer Registry contract.
2. DA-ID format: `DA-OR-000341` (mock) vs `DA-` + 10 digits (Registry). One must win.
3. Priority list source: which system raises "Armyworm infestation" style alerts (Agrilearn, ODK survey result, Supervisor flag)?
4. "Input voucher redeemed this season": which system holds voucher data?
5. Credit application and plot boundary: Credit service and Land Registry contracts do not exist. Accept and hold, or hide the actions until they do?
6. Ethiopian calendar: API stays ISO Gregorian; confirm the UI converts.
7. Farmer confirmation (Confirmed / Tentative): entered by the DA, or from an SMS reply? If SMS reply, we need an inbound SMS webhook.
8. Weekly crop report (task in Today's Plan, quick action "Submit Crop Report"): is this the ODK crop survey, or a separate DA report form?
