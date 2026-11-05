# Security notes and verification

## Local trust boundary

V0.1 is a loopback-only local application, not an Internet-hardened deployment. The backend and Vite listeners bind to `127.0.0.1`; the default trusted browser origins are `http://127.0.0.1:5173` and `http://localhost:5173`, matching the documented quickstart. MySQL accounts are fixed to `127.0.0.1` and scoped to their own databases. Do not expose the development servers, publish MySQL, or reuse local credentials elsewhere.

The real `.env`, storage, encrypted backups, Python/Node dependencies, coverage output, and IDE state are Git-ignored. `.env.example` contains placeholders only. Do not put database URLs, passwords, CSRF secrets, reusable cookies, age private keys, personal files, or server storage paths into source, tests, screenshots, logs, issues, or acceptance evidence.

## Authentication, authorization, and data exposure

- Passwords use Argon2 password hashing. The hidden administrator initializer has no default credential and forces a first-password change.
- Sessions are random, server-side, idle- and absolute-limited, stored hashed in MySQL, and transported in `HttpOnly`, `SameSite=Lax` cookies. The cookie is `Secure` for HTTPS/non-development environments unless explicitly overridden; the example's `SESSION_COOKIE_SECURE=false` is for local HTTP only.
- Password change and logout revoke sessions. Login rate limiting is process-local and therefore not a distributed rate-limit solution.
- Mutations require a trusted Origin and a session-bound CSRF token. The frontend keeps CSRF in memory rather than persistent browser storage.
- The initial-password gate applies globally to business APIs. Multi-tab tabs share the stable session CSRF token.
- `system_admin` has administrative and audit access. `submission_operator` still needs valid per-author grants. `reviewer` remains read-only even if write permissions are granted. `auditor` can read audit logs but cannot read the business dashboard or journal data. Mixed roles unite capabilities except that system-administrator precedence and explicit role exclusions remain enforced.
- Authorization grants have valid-from/to and revocation state. Write operations independently require read access; write-only grants cannot exfiltrate data through mutation responses.
- Manuscript attribution and immutable snapshot authors contain exactly `author_id`, `display_name`, `position`, and `is_corresponding`. Coauthor email, phone, address, ORCID, notes, and server storage paths are not included in manuscript/version/file/dashboard responses.
- Authorship updates submit IDs, positions, corresponding flags, and explicit confirmation only. New coauthor linking requires profile-read authorization and does not reveal whether an unauthorized author ID exists.
- Audit responses use explicit summary-field allowlists. There is no audit create/update/delete API; unsupported mutation methods return the standard error envelope. Business writes and their audit records commit transactionally.

Append-only manuscript snapshots, immutable audit behavior, and file-family history are enforced through service/API boundaries. MySQL triggers or database-level immutability rules are **not** claimed.

## Files and recovery

Uploads are size-limited and validated by content, including structured Office/ZIP/XML checks and malformed/truncated input rejection. Client filename and MIME hints are not trusted. Generated UUID paths prevent client path traversal; downloads use authorized file IDs, descriptor-bound streaming, safe Content-Disposition, and `X-Content-Type-Options: nosniff`. File APIs omit `storage_path` and `stored_filename`.

Manuscript/version state is rechecked under lock during upload. Same-family uploads serialize file-version allocation; stale-version uploads return `409`, and the browser does not automatically repeat the POST. A certain rollback compensates newly moved files. An unknown commit/rollback outcome preserves the formal file and writes a reconciliation manifest entry instead of guessing or deleting it. Reconciliation reports missing, corrupt, and orphaned files without exposing storage paths and never automatically deletes uncertain formal files.

## Backup boundary

Backups stream tar bytes directly into age and publish only completed `.tar.age` files. They include a MySQL dump, storage, `.env.example`, and SHA-256/size manifest entries; they exclude the real `.env`, plaintext credentials, reusable cookies, and `auth_sessions`. Restore requires explicit `RESTORE`, an empty isolated `_test` schema, and empty storage outside live storage. It verifies archive paths, hashes, constrained mysqldump SQL, unqualified table references, row counts, migrations, and restored files.

The age private key must be outside the project, non-symlinked, and inaccessible to group/other users. Loss of the only key means loss of backup recovery. Standalone restore proves source table/row-count stability; the stronger BACKUP-01 proof additionally proves development checksums, schema DDL hashes, and storage hashes unchanged.

## Executable matrix and release gates

Run the complete gate from the project root:

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
bash scripts/verify.sh
```

Focused matrix commands are:

```bash
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent/backend"
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_security_matrix.py tests/test_authorization_boundaries.py -q
ENVIRONMENT=test PYTHONPATH=. ../.venv/bin/python -m pytest \
  tests/test_schema_constraints.py::test_mig_01_empty_upgrade_head_is_cleanly_repeatable -q
cd "/Users/didi/PycharmProjects/AI Journal Submission Agent"
.venv/bin/python scripts/test_backup_restore.py
```

The executable coverage is:

| Matrix area | Enforcement |
|---|---|
| AUTH-01–AUTH-05 | Missing/expired/revoked sessions, CSRF/Origin failures, global first-password gate, stable multi-tab CSRF |
| ROLE-01, AUTHZ-01–AUTHZ-03 | Role unions/exclusions, missing-vs-unauthorized indistinguishability, inactive grants, read-only denial and safe audit failures |
| ISO-01–ISO-06 | Minimal coauthor attribution, real API-created snapshots with poisoned coauthor source data, cross-family substitution, non-enumeration, write-only responses, institution summaries |
| FILE-01–FILE-05 | Spoofed content, hostile filenames, concurrent family versions, rollback/unknown-commit recovery, stale-version races |
| TX-01 | Business/audit rollback atomicity |
| MIG-01 | Empty upgrade to head and repeat upgrade without duplicate effects |
| API-01 | Generated OpenAPI validation plus the real Newman request/assertion collection |
| WEB-01 | Actual local browser DOM/visual inspection and captured Network responses; frontend mocked adapter tests are unit evidence only, not browser E2E |
| BACKUP-01 | Real encrypted backup and isolated restore with source/destination record and hash checks |

Backend coverage floors are 80% overall, 95% permissions, 90% file service, 90% file validation, 90% storage, 85% all services, and 80% API. `scripts/check_coverage.py` enforces each floor. Test/dev database and storage targets must be distinct; destructive guards require an explicit `ENVIRONMENT=test`, explicit loopback database host, fixed `_test` database, and non-live storage before migrations or deletion.

## Residual limitations and dependency advisory

- V0.1 has no distributed login-rate limiter, malware scanner integration, database-trigger immutability, off-site key escrow, or production TLS/reverse-proxy deployment. `scan_status=not_scanned` is an honest state, not a claim that content is malware-free.
- The redundant direct `@faker-js/faker` npm override was removed; Newman still uses the transitive Faker version required by its Postman dependency tree. The full **development** `npm audit` is not clean: it reports five high-severity package entries associated with CVE-2026-73231 in that development-only dependency chain. No supported Postman-compatible fixed release is currently available in the pinned toolchain. Production dependency audit is evaluated separately with `npm audit --omit=dev`; do not describe the full development audit as clean.
- Frontend tests that use an Axios adapter or self-seeded responses verify component behavior only. They are not presented as browser Network or visual acceptance. Actual browser evidence and any blocker are recorded separately in `docs/acceptance-v0.1.md`.
- Acceptance evidence records the exact commands and unresolved gates. A successful CRUD path never substitutes for a failed isolation, migration, file-recovery, backup/restore, coverage, or browser gate.
