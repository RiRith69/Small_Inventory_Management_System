# Warehouse Roll Inventory

Khmer-first inventory tracking for incoming rolls, supplier payment allocations, and Telegram workflows. The website, Telegram bot, and API share PostgreSQL data and backend business rules. This system records roll quantities only; it does not calculate money or track stock leaving the warehouse.

## Features

- Private username/password sign-in; administrators create and manage accounts.
- Server-side sessions in HTTP-only cookies, CSRF headers for state-changing requests, and database-backed login throttling.
- Delivery history with supplier, roll type, delivery date, note, and derived paid/unpaid balances.
- Two seeded roll types: `THICK_GLUE` / កាវក្រាស់ (Thick Glue) and `THIN_GLUE` / កាវស្ដើង (Thin Glue). Stable codes are independent of changeable Khmer and English names.
- Partial or multi-delivery payments with server-side allocation validation, row locking, idempotency keys, and auditable reversals.
- Delivery-date and payment-date filtering, dashboard summaries, paid history, and audit records.
- One-time Telegram account linking; bot permissions resolve from the linked website account.
- Responsive Khmer interface and Khmer Telegram menus.
- PostgreSQL migrations and Docker Compose deployment.

## Requirements

- Docker Desktop with Docker Compose v2 (recommended), or Python 3.13 and Node.js 22 for local development.
- A Telegram bot token from [@BotFather](https://t.me/BotFather) only if you want Telegram integration.

## Quick start with Docker

1. Create a local environment file and replace each `REPLACE_WITH_...` value with a unique random value. Do not commit `.env`.

   ```powershell
   Copy-Item .env.example .env
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Set `POSTGRES_PASSWORD`, `SECRET_KEY`, and `BOT_API_TOKEN` to generated values. For the local host database connection, set the same password in `DATABASE_URL`. URL-safe random values avoid needing URL escaping.

2. Start PostgreSQL, the API, and the website. The backend applies Alembic migrations before serving requests.

   ```powershell
   docker compose up --build -d db backend frontend
   ```

3. Create the first administrator. The command prompts for a username and password without putting the password in shell history. It also seeds example suppliers and ensures both default roll types are present.

   ```powershell
   docker compose exec backend python -m scripts.create_admin
   ```

   The command refuses to create a second initial administrator; use the website to add further accounts.

4. Open `http://localhost:8080`. The API documentation is available at `http://localhost:8000/docs` on the local machine.

If the first administrator already exists but you do not know its password, reset it from the project root without putting the password in shell history:

```powershell
docker compose up --build -d backend
docker compose exec backend python -m scripts.reset_admin_password
```

Enter the existing administrator username and the new password twice at the prompts. This updates the stored password hash and revokes that account's existing sessions. The `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables are only inputs to initial account creation; changing them later does not change an existing database account.

The frontend and API ports are bound to loopback by default. Configure `WEB_PORT`, `BACKEND_PORT`, and `POSTGRES_PORT` in `.env` to change them.

## Local development

PostgreSQL can run in Docker while the API and frontend run with hot reload:

```powershell
Copy-Item .env.example .env
# Set POSTGRES_PASSWORD and update DATABASE_URL to use that password.
docker compose up -d db

Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m scripts.create_admin
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. The development site is usually `http://localhost:5173`.

## Telegram setup

1. In Telegram, create a bot with BotFather and copy its token.
2. Set `TELEGRAM_BOT_TOKEN` and the bot's exact username (without `@`) in `.env`.
3. Set `BOT_API_TOKEN` to a separate random secret. The backend and bot process use this shared secret only for internal API requests.
4. Set `PUBLIC_WEB_URL` to the website's public HTTPS URL and `TELEGRAM_BOT_USERNAME` to the BotFather username.
5. Start the bot using the Compose profile:

   ```powershell
   docker compose --profile telegram up --build -d telegram-bot
   ```

6. Sign in to the website, open **គណនី និង Telegram**, and choose **ភ្ជាប់ Telegram**. Open the one-time link from the same Telegram account. The code expires after a short period and can only be used once.
7. Create additional website users in **គ្រប់គ្រងអ្នកប្រើ**. They link Telegram from their own account page.

Telegram long polling requires the bot container to reach Telegram's API. A bot running only on a local machine is not reachable by Telegram users unless that machine has outbound internet and the bot is running. The application does not store Telegram state separately from PostgreSQL; the bot calls the same backend services used by the website.

## Accounts, permissions, and corrections

- There is no public registration page.
- The initial catalogue contains the two Khmer glue types with stable English codes. Administrators may update each Khmer/English display name independently or deactivate a type; codes are immutable and duplicate codes are rejected.
- Roll types referenced by delivery history cannot be deleted. Deactivate them to prevent new selections while keeping historical names and reports intact.
- Administrators create users, assign roles, deactivate accounts, reset passwords, revoke Telegram links, and configure payment/edit/delete permissions in **ការកំណត់សិទ្ធិ**.
- Warehouse users can record deliveries and view history. They can confirm payments only if an administrator enables that role.
- A delivery's paid and unpaid quantities are derived from its active payment allocations.
- Payment confirmation recalculates unpaid quantities on the server. Partial payments leave the remainder unpaid.
- Payments are retained. An administrator may reverse a payment with a required reason; the original payment and its audit record remain visible.
- Delivery edits and deletes require permission. A delivery cannot be deleted while active payment allocations remain.

## Inventory and payment workflow

1. **Record a delivery.** Choose the supplier and one active roll type, enter a positive whole-roll quantity, the arrival date, and optionally a note. The backend stores one delivery row linked to its supplier and roll type; paid quantities never replace or duplicate that row.
2. **Review balances.** Delivery, dashboard, and unpaid views derive quantities from the delivery record and payment allocations. Paid quantity is the sum of allocations attached to that delivery, excluding reversed payments; unpaid quantity is received minus paid. Filters use supplier, roll type, and inclusive delivery-date ranges.
3. **Preview payment.** Select a supplier, one roll type, and optionally a delivery-date range. The web and Telegram workflows show received, paid, and unpaid totals for that selection.
4. **Allocate payment.** Select one or more delivery records of that same supplier and roll type. Partial allocations are allowed; a payment can span dates but cannot mix roll types. The server locks the delivery records, recalculates unpaid quantities, and rejects supplier/type mismatches or overpayment before saving allocations atomically.
5. **Confirm and refresh.** Payment history is linked back to the original deliveries. Web views refresh after confirmation; Telegram reads the same API and database. A reversal records a reason and restores the allocated quantity to unpaid without deleting the payment history.

Example: receive 20 rolls of កាវក្រាស់ and allocate 12. The balance for that supplier and type is received **20**, paid **12**, unpaid **8**. Deliveries of កាវស្ដើង are not affected.

## Start, stop, and inspect the platform

Docker Compose commands are run from the project root in PowerShell:

```powershell
# Start the database, API, and web app
docker compose up --build -d db backend frontend

# Check service status and API health
docker compose ps
Invoke-RestMethod http://localhost:8000/healthz

# Follow application logs
docker compose logs -f backend frontend

# Stop containers but retain the database volume
docker compose down
```

The default website is `http://localhost:8080`, API documentation is `http://localhost:8000/docs`, and health status is `http://localhost:8000/healthz`. `docker compose down` does not erase the database volume. Do not use `docker compose down -v` unless intentionally discarding all local database data.

For local development without Docker, start PostgreSQL using the configured `DATABASE_URL`, then run Alembic, the API (`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from `backend`), and Vite (`npm run dev` from `frontend`) in separate terminals. See [Local development](#local-development) for setup commands.

## Project layout and data flow

- `backend/app/api/` — website and authenticated internal Telegram endpoints.
- `backend/app/services/` — shared delivery, payment, catalogue, dashboard, authorization, and audit rules.
- `backend/app/models/` and `backend/alembic/versions/` — database models and forward-only PostgreSQL migrations. Migration `0004_roll_type_localization` adds stable codes, localized names, and seeds the two glue types.
- `backend/tests/` — isolated API and business-workflow tests.
- `frontend/src/` — React website, typed API client, and Khmer/English localization resources in `locales/`.
- `telegram_bot/` — Telegram conversations; it calls the internal API rather than reading or calculating database totals itself.
- `docker-compose.yml` and component Dockerfiles — local/deployable database, API, website, and optional Telegram bot.

The website and bot share the same API services and PostgreSQL tables. Payments refer to allocations, allocations refer to deliveries, and each delivery has a required `roll_type_id`; this preserves the type identity through payment, reporting, and historical views.

## Tests and checks

Run backend tests from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Build and check the frontend from `frontend`:

```powershell
npm ci
npm run build
npm audit
```

The automated backend suite uses an isolated SQLite database for fast API/service tests. The production schema and allocation safety triggers are PostgreSQL-specific and are installed by Alembic; use PostgreSQL for deployment.

## Production deployment

- Set `ENVIRONMENT=production`, `COOKIE_SECURE=true`, HTTPS-only public URLs, a strong `SECRET_KEY`, a strong `BOT_API_TOKEN`, and a non-placeholder PostgreSQL password before starting the production API.
- Configure `CORS_ORIGINS` with only the website origin(s). Keep the backend and PostgreSQL ports private; expose the frontend through a TLS-terminating reverse proxy.
- The API refuses to start in production when required secrets or secure cookies are missing.
- Use a secret manager or protected deployment environment for credentials. Never place real credentials in `docker-compose.yml`, source code, screenshots, or commit history.
- Plan database backups and restore rehearsals. Retain backups away from the server that hosts the database.

## PostgreSQL backup and restore

Create a plain SQL backup without printing credentials:

```powershell
docker compose exec -T db sh -c 'pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' | Set-Content -Encoding utf8 .\warehouse-backup.sql
```

Restore into a clean database of the same application version. Do not import over a live database without first making a separate backup and planning the migration:

```powershell
Get-Content .\warehouse-backup.sql | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

For large deployments, prefer binary-format backups (`pg_dump -Fc`) and test `pg_restore` procedures against a separate database.

## API overview

The interactive API reference is at `/docs`. Main route groups include:

- `/api/auth` — login, logout, current session, and password changes.
- `/api/users`, `/api/settings`, `/api/audit` — administrator operations and audit history.
- `/api/catalog`, `/api/suppliers`, `/api/roll-types` — configurable warehouse catalogue.
- `/api/deliveries` — delivery capture, filtering, summaries, and corrections.
- `/api/payments` — unpaid previews, confirmation, paid history, detail, and reversals.
- `/api/dashboard` — database-derived dashboard totals and activity.
- `/api/telegram` — authenticated website linking and unlinking.
- `/api/bot` — internal Telegram API protected by `X-Bot-Token` and Telegram-ID resolution.

The internal bot API is not a substitute for Telegram verification. The bot takes the numeric user ID from Telegram updates, and the backend maps it to an active linked website user before each protected operation.
