# Project Review and Completion Notes

## Summary

The workspace initially contained a structured FastAPI/SQLAlchemy backend and migrations, but it had no application entry point, frontend source, functioning Telegram bot, deployment configuration, or meaningful automated tests. Several existing backend paths also had integration and data-integrity problems that could not be discovered from source compilation alone.

The implementation now connects the existing services to a complete React/Vite interface, FastAPI runtime, PostgreSQL deployment, and aiogram bot. All recorded inventory and payment calculations use the backend database and service layer.

## Findings addressed

1. **Application not runnable:** added `app.main:app`, all routers, CORS, consistent exception handlers, health check, and a secure interactive first-admin command.
2. **Incomplete payment migrations:** added the missing delivery idempotency columns, request fingerprints, Telegram-link attempt table, and migration updates for payment allocation checks.
3. **Payment reversal database guard mismatch:** allocation invariants now ignore reversed payments, allowing a safely reversed quantity to become unpaid and be paid again. Delivery quantity reductions are guarded at the database level as well as in service validation.
4. **Idempotency-key misuse:** deliveries and payments bind idempotency keys to a normalized request fingerprint. Reusing a key for a different actor or payload is rejected.
5. **Unpaid filter query defect:** unpaid row selection referenced the allocation subquery twice without joining it correctly. It now filters using the already joined paid-total expression; coverage includes partial, range, and reversal scenarios.
6. **ORM mapper ambiguity:** the user/Telegram relationship did not identify which of two user foreign keys it represented. Explicit foreign-key mapping fixes ORM initialization.
7. **Unsafe edit/payment races:** delivery corrections/deletes and payment reversals lock affected rows; payment allocation continues to lock deliveries before recalculating remaining quantities.
8. **Unbounded history queries:** payment and audit history now use database count/limit/offset rather than loading the entire history before slicing.
9. **Incomplete user operations:** the administrator interface now supports user creation, role changes, deactivation/reactivation, password resets, and Telegram-link revocation.
10. **Unverified client and bot behavior:** added a Khmer React interface with session-cookie/CSRF handling and a Telegram bot that calls the authenticated internal API for linking, deliveries, summaries, unpaid previews, and permitted payment confirmation.
11. **Roll type identity and localization:** roll types now use immutable unique codes, separate Khmer and English names, and updated timestamps. Migration `0004_roll_type_localization` safely renames legacy types, preserves existing IDs referenced by deliveries, and seeds `THICK_GLUE` / កាវក្រាស់ and `THIN_GLUE` / កាវស្ដើង.
12. **Mixed-type payment allocations:** payment confirmation now selects one roll type and rejects allocations from another type. Reports derive received, paid, and unpaid totals per type and supplier/type pair.
13. **Consistent type labels:** website/API and Telegram catalogue responses share the same Khmer names, with English names retained for localization. The frontend includes Khmer and English locale resources.

## Main implementation areas

- `backend/app/main.py` — application runtime and routes.
- `backend/app/services/` — shared inventory, payment, authorization, Telegram, and audit logic.
- `backend/alembic/versions/` — PostgreSQL schema history and data-integrity guards.
- `frontend/src/` — responsive Khmer UI with login, dashboard, daily deliveries, unpaid allocation preview, paid details/reversals, account linking, settings, user management, audit history, and `locales/` language resources.
- `telegram_bot/` — aiogram long-polling bot and stateful Khmer conversation flows.
- `docker-compose.yml` — PostgreSQL, API, frontend, and opt-in Telegram bot services.

## Validation performed

- Python compile and application import checks passed.
- Backend automated tests passed: **13 passed**. The cases exercise session authentication, user creation, API authorization, Telegram linking/reuse/expiry, shared website/bot delivery records, supplier isolation, identical website/bot localized catalogue values, localized default roll types, type-filtered balances, same-type payment allocations, partial and multi-day payments, idempotency (including concurrent replay), reversals, and warehouse payment permissions.
- PostgreSQL 17 migrations were applied to disposable local clusters. Fresh installs seed exactly two types, repeat initialization is idempotent, legacy delivery foreign keys remain intact through localization, and reverse-and-repay/over-allocation/quantity-integrity guards were checked.
- Frontend TypeScript/Vite production build passed.
- `npm audit` reported **0 vulnerabilities** after upgrading the affected React Router and Tailwind dependencies.
- Live Telegram delivery was not exercised because it requires a real BotFather token and a reachable Telegram deployment. The bot API, authorization, and shared data workflow are covered locally.
- Docker image builds could not be run in this environment because the Docker Desktop engine was unavailable.

## Operational notes

- Copy `.env.example` to `.env` and replace every `REPLACE_WITH_...` placeholder before deployment. Keep `.env` private.
- Initial migrations run automatically in the backend Compose service; use `python -m scripts.create_admin` once to initialize the administrator and example catalogue.
- The bot uses Telegram long polling and is in the `telegram` Compose profile so it does not start until credentials are configured.
- The automated tests use SQLite for isolation. PostgreSQL remains required for deployment because the Alembic allocation guards use PostgreSQL triggers and `SELECT FOR UPDATE` semantics.
- The first administrator bootstrap ensures both default roll types are present. Normal deployments create them through Alembic migration `0004`; legacy roll type IDs are preserved when migrating so existing deliveries keep their references.
- A payment may cover multiple dates, but all its allocations must use the same supplier and roll type. Historical roll types cannot be deleted when deliveries reference them; administrators should deactivate them instead.
- The workflow and PowerShell run/stop guide is in [README.md](./README.md).
- The interface does not represent total received as physical stock and does not implement prices or currency accounting.
