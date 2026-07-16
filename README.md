# UrbanDash Complaint Triage

Ingests raw complaints from the app, email, and Twitter DMs, classifies them
with the Groq API (category, urgency, routed team, reasoning), and shows
the results in a reviewable ops dashboard queue with human override.

## Quick start

Requirements: Docker + Docker Compose. Nothing else needs installing locally.

```bash
cp .env.example .env
# edit .env and put your real key in GROQ_API_KEY

docker compose up --build
```

Then open:

- **Dashboard:** http://localhost:8007
- **API:** http://localhost:4040 (interactive docs at http://localhost:4040/docs)

On first boot the backend seeds the database with ~30 realistic, messy
example complaints (sarcasm, bundled multi-issue messages, praise mistaken
for a complaint, hedged food-safety language, test/QA noise, emoji-only
low-signal messages, driver-originated complaints, Hinglish, and legal/MRP
overcharge cases). They're seeded **unclassified** — use the "Classify all
unclassified" button in the sidebar (or classify one at a time) to run them
through the live Groq API pipeline and populate the queue.

If `GROQ_API_KEY` is missing or invalid, ingestion still works; only the
`/classify` step will return a clear error, both in the API response and as
a toast in the UI.

## Architecture

```
┌─────────────┐      HTTP       ┌─────────────┐      SQL       ┌─────────────┐
│  frontend   │ ───────────────>│   backend   │ ───────────────>│  postgres   │
│  (nginx)    │  :4040          │  (FastAPI)  │  :5432          │     db      │
│  :8007      │                 │  :4040      │                 │             │
└─────────────┘                 └──────┬──────┘                 └─────────────┘
                                        │ HTTPS
                                        v
                                 Groq API
```

Three containers, orchestrated by `docker-compose.yml`:

- **frontend** — static HTML/CSS/JS ops dashboard, served by nginx on `8007`.
- **backend** — FastAPI service on `4040`. Owns ingestion, classification
  (calls the Groq API), the queue, and status/override updates.
- **db** — PostgreSQL 18.

### Why Postgres over SQLite

The brief allowed either. Postgres was chosen because this is modeled as a
real internal ops tool: multiple support agents would realistically hit the
API concurrently (filtering the queue, overriding classifications, updating
statuses) while the backend is also writing new classification rows from
async ingestion. Postgres handles concurrent writers safely out of the box;
SQLite's single-writer lock is a worse fit for that access pattern even at
small scale, and running Postgres as its own container costs nothing extra
in a Compose setup. It also keeps the door open for JSONB / full-text search
on complaint bodies later without a migration to a different engine.

## Data model

**complaints**
| column | type | notes |
|---|---|---|
| id | string (PK) | short generated id |
| channel | enum | `app`, `email`, `twitter_dm` |
| customer_identifier | string | name / handle / driver id |
| complainant_type | enum | `customer`, `driver` |
| raw_message | text | the raw inbound message |
| status | enum | `open`, `in_progress`, `resolved` |
| created_at / updated_at | timestamp | |

**classifications** (one-to-many with complaints — a single message that
bundles multiple distinct issues produces multiple linked rows, `sub_index`
0, 1, 2…)
| column | type | notes |
|---|---|---|
| id | string (PK) | |
| complaint_id | string (FK) | |
| sub_index | int | order within a bundled complaint |
| category | string | see categories below |
| urgency | enum | `low`, `medium`, `high`, `critical` |
| routed_team | string | `support`, `ops`, `trust_and_safety`, `finance`, `hr_driver_relations`, `legal`, `none` |
| reasoning | text | short explanation from Groq |
| is_noise | bool | true for praise / test-QA noise / low-signal — not routed to a team |
| overridden | bool | true once a human has manually edited this row |
| created_at / updated_at | timestamp | |

Categories used by the classifier: `delivery_delay`, `food_quality`,
`food_safety`, `billing_dispute`, `order_mixup`, `coverage_request`,
`praise`, `driver_safety`, `legal_compliance`, `account_management`,
`test_noise`, `low_signal`, `other`.

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/complaints/ingest` | Create a raw complaint (`channel`, `customer_identifier`, `complainant_type`, `raw_message`). |
| POST | `/complaints/{id}/classify` | Calls Groq to classify (or re-classify) a complaint into one or more linked issues. |
| GET | `/queue` | Filterable queue: `?team=`, `?urgency=`, `?status=`, `?include_noise=true|false`. Excludes noise by default. |
| GET | `/complaints/{id}` | Full complaint detail with all its classifications. |
| GET | `/complaints` | List all complaints (used by the "unclassified" view). |
| PATCH | `/complaints/{id}/status` | Update status: `open`, `in_progress`, `resolved`. |
| PATCH | `/classifications/{id}` | Human override — reassign category/urgency/team/reasoning/noise flag on a single classification. |
| GET | `/health` | Liveness check, used by the dashboard's connection indicator. |

Full interactive schema/docs at `/docs` once the backend is running.

## Error handling

- Empty/whitespace-only messages are rejected on ingest (422) and on
  classify.
- Malformed channel / complainant_type values are rejected with a clear
  validation message.
- If the Groq API call fails (network error, bad key, non-2xx response,
  or an unparseable/empty response body), `/complaints/{id}/classify`
  returns `502` with the underlying reason instead of crashing or silently
  storing garbage — the frontend surfaces this as a toast.
- If Groq returns a category/urgency/team outside the known enum, the
  backend falls back to a safe default (`other` / `medium` / `support`)
  rather than rejecting the whole classification, so one malformed field
  doesn't lose an otherwise-good classification.

## Frontend design notes

The dashboard is a dark "dispatch room" console themed around UrbanDash's
own delivery-manifest vocabulary: queue items render as manifest-stub
ticket cards with a rotated dashed "stamp" carrying the urgency signal
(critical / high / medium / low / filtered). All colors live in one
`:root` block in `frontend/css/style.css` under the `# COLOR PALETTE`
comment header — change the palette there to reskin the whole app. Every
other design-relevant block (typography, layout/spacing, components, JS UI
state) is marked with a `# SECTION NAME` comment header in the relevant
CSS/JS file for quick reskinning.

## Repo layout

```
urbandash/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py         # FastAPI routes
│       ├── models.py       # SQLAlchemy models
│       ├── schemas.py      # Pydantic request/response schemas
│       ├── classify.py     # Groq API call + validation
│       ├── seed_data.py    # starter complaint dataset
│       └── database.py     # DB engine/session
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── index.html
    ├── css/style.css
    └── js/app.js
```
