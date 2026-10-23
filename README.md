# Xonovate Challenge Tracker

A local Django application for running **Building Xonovate: 100 Days to GH₵200,000** and publishing a privacy-safe public progress page.

It is a single-operator workspace. Financial records stay behind authentication, while the public landing page is read-only and shows only revenue that has been explicitly approved for public display.

## Current challenge

| Detail | Value |
| --- | --- |
| Challenge | Building Xonovate: 100 Days to GH₵200,000 |
| Start | 24 October 2026 |
| End | 31 January 2027 |
| Duration | 100 days, inclusive |
| Target | GH₵200,000.00 |
| Business units | Xonovate Technologies; Xonovate Code Champions |

The initial migration creates the challenge, the two active business units, and the starting revenue and expense categories. It does not create sample transactions. Figures stay at zero until real records are entered.

## What the app does

- Tracks actual qualifying customer revenue against a gross revenue target.
- Records operating expenses, payment status, and optional receipt files.
- Keeps loans, owner contributions, grants, refunds, and internal transfers separate from revenue.
- Provides dashboard, revenue, expense, report, history, and simulator views.
- Exports financial data to CSV for spreadsheet use.
- Publishes a sanitized public progress page without exposing customer or internal financial details.
- Keeps Django Admin available for low-level corrections and audit review.

## Requirements

- Python 3.13 (tested with Python 3.13.5)
- Windows PowerShell, macOS, or Linux
- No internet connection at runtime; Bootstrap and Bootstrap Icons are stored locally

## First-time setup

Open PowerShell in the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

If PowerShell blocks activation, you can call the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

Open:

- Public progress page: http://127.0.0.1:8000/
- Private workspace: http://127.0.0.1:8000/dashboard/
- Sign in: http://127.0.0.1:8000/login/
- Django Admin: http://127.0.0.1:8000/admin/

## Running the app later

```powershell
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

Run migrations after pulling changes that include new migration files:

```powershell
python manage.py migrate
```

## Daily workspace

The main navigation has five sections:

1. **Dashboard** - challenge progress, business-unit totals, and recent activity.
2. **Revenue** - record and review collected customer revenue.
3. **Expenses** - record and review operating costs and obligations.
4. **Reports** - review filtered totals and download CSV exports.
5. **Settings** - edit the single challenge and manage revenue and expense categories.

Supporting tools remain secondary to those sections:

- **Other financial movements** - non-revenue receipts and refunds.
- **Transaction history** - a combined view of revenue and expenses.
- **Scenario simulator** - planning estimates that never affect real totals or the public page.

## Financial rules

- The target counts only qualifying customer revenue with status **Received** or **Partially refunded**.
- A partially refunded transaction counts as `amount - refunded_amount`.
- Fully refunded and voided transactions contribute zero but remain in history.
- Revenue dates must fall inside the challenge period.
- Expenses are tracked separately and never reduce the gross revenue target.
- Loans, owner contributions, investments, grants, and other non-revenue receipts never count toward the target.
- The simulator is isolated from actual totals, reports, and public progress.
- Duplicate revenue entries with the same date, amount, business unit, category, and description are blocked unless edited or deliberately distinguished.

All figures are calculated from the current database state, so corrections made in Django Admin are reflected immediately.

## Public page privacy

The page at `/` is available without sign-in and always reflects the single configured challenge.

- It shows only approved fields such as date, business unit, public description, and amount.
- Revenue rows appear only when **Public visibility** is enabled.
- Customer names, internal notes, private descriptions, references, and receipts are never shown.
- If no public description is supplied, a safe category-based summary is used.
- Aggregate challenge totals include all qualifying revenue; the itemized table is limited to approved public records.

## Settings and categories

Settings edits the single configured challenge: description, start date, end date, target amount, and status.

Revenue and expense categories can be added, edited, and deactivated. Historical records keep their original category links, so retiring an unused category does not alter past totals.

## Reports and CSV exports

Reports can be filtered by date range and business unit. The workspace provides CSV exports for:

- Overall challenge summary
- Qualifying revenue
- Revenue by business unit
- Expenses
- Publicly approved revenue

The transaction history view also provides a combined revenue-and-expense export.

Exports use UTF-8 with a byte-order mark for spreadsheet compatibility and guard against spreadsheet formula injection.

## Receipts

Expense receipts may be PDF, JPG, JPEG, or PNG files up to 5 MB. Files are stored under `media/receipts/YYYY/MM/` and are served only to signed-in users. The public page never links to them.

## Django Admin

Django Admin is a maintenance interface, not the primary workspace. It can:

- Correct challenge details and category records
- Inspect or correct financial records
- Search and filter records
- Review read-only audit log entries
- Void selected revenue transactions or mark them fully refunded
- Void selected expenses

Deletion is disabled for challenges and financial records. Prefer status, refund, or void corrections so history is preserved.

## Tests

Run the full suite with:

```powershell
.\.venv\Scripts\python.exe manage.py test tracker -v 2
```

Run Django's system checks and confirm migrations are current with:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

The test suite covers the challenge period and duration, single-challenge behavior, the active business units, public privacy, authentication redirects, revenue and expense calculations, refunds and voids, duplicate protection, non-revenue isolation, filtering, CSV exports, simulator isolation, Admin synchronization, and empty datasets.

## Backup and restore

All local financial data is in `db.sqlite3`. Uploaded receipts are in `media/`.

To back up:

1. Stop the development server.
2. Copy `db.sqlite3` and the `media/` folder to a secure location.
3. Optionally copy the complete project folder, excluding `.venv`.

To restore:

1. Stop the server.
2. Replace `db.sqlite3` and `media/` with the backup copies.
3. Start the server and verify the dashboard.

Do not store financial backups in a public folder or unencrypted cloud location.

## Configuration

Defaults are in `config/settings.py`:

- SQLite database: `db.sqlite3`
- Time zone: `Africa/Accra`
- Currency: `GHS`
- Public landing page at `/`
- Login required for financial management pages
- Private dashboard at `/dashboard/`
- Local static and media files

Optional environment variables:

```powershell
$env:DJANGO_SECRET_KEY = "replace-with-a-long-random-value"
$env:DJANGO_DEBUG = "0"
```

`ALLOWED_HOSTS` is intentionally limited to `127.0.0.1` and `localhost`. This project is configured for local use, not public internet hosting. If it is ever deployed, replace the default secret key, disable debug mode, configure HTTPS, and serve uploaded media privately.

## Project layout

```text
config/                 Django project settings and root URLs
tracker/
  models.py             Challenge, business unit, transaction, expense, movement, audit models
  services.py           Authoritative totals, reports, and simulator calculations
  forms.py              Validated workspace forms
  views.py              Public page, dashboard, records, reports, settings, tools
  urls.py               Application routes
  admin.py              Django Admin configuration and maintenance actions
  signals.py            Audit logging
  migrations/           Database schema and initial challenge data
  templates/tracker/    Private workspace, public landing, and login templates
  templatetags/         Template helpers
  tests.py              Automated test suite
static/
  css/app.css           Application styling
  vendor/               Local Bootstrap and Bootstrap Icons
db.sqlite3              Local database (created after migration)
media/                  Uploaded receipts
```
