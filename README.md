# Xonovate Challenge Tracker

A local Django application for tracking the **Building Xonovate: 100 Days to GH₵200,000** challenge. It records actual customer revenue, expenses, supporting financial movements, and a sanitized public progress page.

The application is designed for one founder/operator on one local computer. The public landing page is read-only and does not require sign-in. Financial management remains private. Django Admin is available for low-level maintenance.

## Requirements

- Python 3.13 (tested with Python 3.13.5)
- Windows PowerShell, macOS, or Linux
- No internet connection is required at runtime. Bootstrap and Bootstrap Icons are stored locally.

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

Open http://127.0.0.1:8000/ for the public progress page. Sign in at http://127.0.0.1:8000/login/ with the account created above to manage the challenge.

The database migration creates:

- The challenge: **Building Xonovate: 100 Days to GH₵200,000**
- Start date: **24 October 2026**
- End date: **31 January 2027**
- Inclusive duration: **100 days**
- Target: **GH₵200,000.00**
- The two active business units: **Xonovate Technologies** and **Xonovate Code Champions**
- Initial revenue and expense categories

It does **not** create sample transactions. Figures begin at zero until real records are entered.

## Daily use

The workspace has five main sections:

1. **Dashboard** — target progress, business-unit totals, and recent revenue and expenses.
2. **Revenue** — record and review actual collected customer revenue.
3. **Expenses** — record and review operating costs.
4. **Reports** — review a simple challenge report and export CSV files.
5. **Settings** — edit the single challenge, manage categories, and open supporting tools.

Supporting tools include other financial movements, transaction history, and the scenario simulator. They remain secondary to the five main sections.

### Financial rules

- The revenue target counts only qualifying revenue with status **Received** or **Partially refunded**.
- A partially refunded transaction counts as `amount - refunded_amount`.
- Revenue is constrained to the challenge dates.
- Expenses are shown separately and are **not deducted** from gross qualifying revenue.
- Loans, owner contributions, grants, and other non-revenue receipts never count toward the revenue target.
- Refunded and voided transactions contribute zero. Records are preserved rather than deleted.
- The challenge has a 100-day inclusive duration.

### Public page privacy

The public landing page at `/` does not require sign-in. It only displays a revenue transaction when **Public visibility** is enabled. The page never displays customer names, internal notes, internal descriptions, references, or receipts. If no public description is supplied, a safe category-based summary is shown instead.

The public page always reflects the single configured challenge. Aggregate challenge totals include all qualifying revenue; the transaction table is limited to records explicitly approved for public viewing.

### Receipts

Expense receipts may be PDF, JPG, or PNG files up to 5 MB. They are stored under `media/receipts/` and are only served to signed-in users. The public page never links to them.

## Django Admin

Open http://127.0.0.1:8000/admin/ with a staff/superuser account.

Django Admin can:

- Correct challenge details and categories
- Add or correct financial records
- Search and filter records
- Review read-only audit logs
- Void or refund selected revenue transactions
- Void selected expenses

Deletion is disabled for challenges and financial records. Use void/status corrections to preserve history.

Changes made in Django Admin are reflected immediately because all figures are calculated from the database on each request.

## Tests

Run the complete suite with:

```powershell
.\.venv\Scripts\python.exe manage.py test tracker -v 2
```

The suite covers the 100-day challenge, single-challenge settings, the two active business units, public landing privacy, login redirects, revenue and expense calculations, business-unit attribution, refunds and voids, duplicate protection, non-revenue isolation, filtering, CSV exports, simulator isolation, Admin synchronization, and empty datasets.

## CSV exports

Reports include overall, revenue, revenue by business unit, expenses, and publicly approved transactions. CSV exports use UTF-8 with a byte-order mark for spreadsheet compatibility and protect against spreadsheet formula injection.

## Backup and restore

All local financial data is in `db.sqlite3`. Uploaded receipts are in `media/`.

To make a backup:

1. Stop the development server.
2. Copy `db.sqlite3` and the `media/` folder to a secure location.
3. Optionally copy the complete project folder, excluding `.venv` if desired.

To restore:

1. Stop the server.
2. Replace `db.sqlite3` and `media/` with the backup copies.
3. Start the server and verify the dashboard.

Do not store financial backups in a public folder or cloud location without encryption.

## Configuration

Defaults are in `config/settings.py`:

- SQLite database: `db.sqlite3`
- Time zone: `Africa/Accra`
- Currency: `GHS`
- Public landing page at `/`
- Login required for all financial management pages
- Private dashboard at `/dashboard/`
- Static assets served locally

Optional environment variables:

```powershell
$env:DJANGO_SECRET_KEY = "replace-with-a-long-random-value"
$env:DJANGO_DEBUG = "0"
```

`ALLOWED_HOSTS` is intentionally limited to `127.0.0.1` and `localhost`. This project is configured for local use, not public internet hosting.

## Project layout

```text
config/                 Django project settings and root URLs
tracker/
  models.py             Challenge, ARM, revenue, expense, movement, audit models
  services.py           Authoritative totals, progress, and simulator logic
  forms.py              Validated frontend forms
  views.py              Dashboard, records, reports, settings, public landing page
  urls.py               Application routes
  admin.py              Django Admin configuration
  signals.py            Audit logging
  templates/tracker/    Private workspace and public landing templates
  tests.py              Automated test suite
static/
  css/app.css           Application styling
  vendor/               Local Bootstrap and Bootstrap Icons
db.sqlite3              Local database (created after migration)
media/                  Locally uploaded receipts
```
