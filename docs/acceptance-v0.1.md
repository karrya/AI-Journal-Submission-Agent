# V0.1 final acceptance

**Acceptance date:** 2026-11-05 (evidence timestamp 2026-11-05T13:22:15Z)  
**Result:** **PASS — all required V0.1 gates executed successfully.** The residual limitations below do not represent skipped or failed required gates.

The tested change is based on commit `fddff14` plus the Task 18 documentation and reviewed minor hardening changes. The Task 18 report records the implementation and verification scope. No real password, database URL, session token, age private key, personal document, or server storage path is included here.

## Environment

- macOS on arm64; Homebrew `mysql@8.0` 8.0.46 (final runtime), Python 3.13.3, Node 26.13.0, npm 11.20.0.
- Backend: `/Users/didi/PycharmProjects/AI Journal Submission Agent/.venv/bin/python`.
- Browser: actual Google Chrome 156.0.8078.80, headless, driven by temporary `playwright-core` tooling outside the application dependencies.
- Committed, sanitized request-level Network evidence, the executable browser harness, and synthetic-data screenshots are under [`docs/evidence/v0.1/browser/`](evidence/v0.1/browser/). Original raw logs and non-secret snapshots remain under `.superpowers/sdd/2026-11-04-v0-1-implementation/acceptance/`; that workspace is not a release artifact and is not committed.

## 1. Clean installation from the documentation

Commands executed from the documented project root:

```bash
.venv/bin/python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m alembic check
cd ..
.venv/bin/python scripts/create_admin.py
bash scripts/verify.sh
```

The existing provisioned root `.env` was not read into evidence, modified, staged, or printed. Consequently, the credential-rotating administrative bootstrap was not rerun. Instead, the existing least-privilege `asa_test` connection was used internally, without printing its URL, to drop and recreate **only** `academic_submission_agent_test` as a fresh empty schema with the documented utf8mb4 collation. No other database was targeted. Storage was a newly created `/tmp` directory.

Observed results:

- Pinned backend/frontend dependency installation passed (`dependency-install.log`).
- The schema began empty. Two `upgrade head` calls reached the same head; the second log contains no `Running upgrade` operation. `alembic check` passed.
- Exactly **18 application tables plus `alembic_version`** (19 total) were inspected after migration.
- The actual `create_admin.py` CLI received a generated username and hidden initial-password input. First login returned `must_change_password=true`; `POST /api/v1/auth/change-password` returned 204; a fresh login with the replacement password returned 200 and `must_change_password=false`. Generated passwords were neither written to evidence nor printed.
- The clean temporary backend used port 8002 and was terminated afterward; temporary storage was removed.
- One harness attempt incorrectly included the frontend-only `confirm_password` field. The API correctly rejected that extra field; the harness was corrected to the documented `current_password`/`new_password` API schema and the complete clean-install sequence was rerun from another fresh schema. This was not a product failure.

## 2. Complete verification, coverage, and contracts

`bash scripts/verify.sh` passed after clean installation, again on the final repaired MySQL runtime, and after the fix-round origin/snapshot changes (`verify-clean.log`, `verify-final-pre-doc.log`, `verify-fix-round-1.log`).

| Gate | Result |
|---|---|
| Ruff and mypy | Passed; all checks clean |
| Backend pytest | **459 passed**, 0 failed (latest final run 27.89 s) |
| Focused executable security matrix | **36 passed**, 0 failed (`test_security_matrix.py` plus `test_authorization_boundaries.py`) |
| Backend overall coverage | **95.69%** (floor 80%) |
| Permissions coverage | **98.65%** (floor 95%) |
| File service coverage | **91.83%** (floor 90%) |
| File-validation coverage | **90.23%** (floor 90%) |
| Storage coverage | **94.78%** (floor 90%) |
| Combined services coverage | **93.51%** (floor 85%) |
| API coverage | **96.91%** (floor 80%) |
| OpenAPI | Generated, validated with `openapi-spec-validator`, and `git diff --exit-code` clean |
| Newman | **40/40 requests, 97/97 assertions**, 0 failures; isolated backend port 8001 and temporary storage |
| Frontend unit tests | **22 files, 122 tests passed**, repeated for the coverage run |
| Frontend statement coverage | **82.66%** (1645/1990) |
| Frontend branch coverage | **85.84%** (1946/2267) |
| Frontend function coverage | **77.61%** (437/563) |
| Frontend line coverage | **86.52%** (1516/1752) |
| Frontend production build | `vue-tsc --noEmit && vite build` passed; latest final Vite build completed in 2.24 s |

The redundant direct Faker override was absent during these successful Newman runs. Production `npm audit --omit=dev` returned zero vulnerabilities. Full development `npm audit` returned five high-severity entries, as detailed under limitations.

## 3. Persistence and MySQL/web restart acceptance

A synthetic owner and poisoned coauthor, manuscript, immutable version 2, and PDF file were created through the real API against the fresh `_test` schema and temporary storage. Disposable operator and auditor accounts and an owner-only operator grant were added for role checks. Before restart, direct ORM and filesystem checks confirmed all four records, current-version linkage, byte count, and SHA-256.

The authorized maintenance command and both checked-in startup scripts were exercised:

```bash
brew services restart mysql@8.0
bash scripts/dev_backend.sh
bash scripts/dev_frontend.sh
```

The backend and frontend were both running before the MySQL restart and were then stopped and restarted using only their acceptance PIDs/listeners. Post-restart checks included fresh API login, manuscript/version/file reads, and an authorized download.

| Persistence check | Before | After |
|---|---|---|
| Author, manuscript, version, file records | Present | Present |
| Manuscript current version is accepted v2 | True | True |
| File byte count | 69 | 69 |
| File SHA-256 | `cfa3181c1ee36e8bce5e39f84959f4558ea7ba32c0e4539a8ab3c8ce8c716ec6` | Identical |
| Authorized download SHA-256 | Same fixture hash | Identical after restart |

`persistence-before.json` and `persistence-after.json` are byte-identical. The final MySQL service was left started; acceptance web processes were stopped.

### Resolved environmental incident

The first authorized restart exposed a Homebrew runtime defect: `mysqld` 8.0.42 could not load the removed Abseil `2407.0.0` dynamic library. The service therefore did not return and no persistence/browser success was claimed for that attempt. `mysql-homebrew-repair.log` and `mysql-homebrew-repair-mirror.log` record the repair. The package was upgraded without deleting or initializing any data directory; the reachable Tsinghua bottle mirror was used after the default download stalled. MySQL 8.0.46 then started successfully. Development and test schemas were both inspected before rerunning the complete persistence sequence from a fresh test schema. The final restart and all subsequent gates passed.

## 4. Actual browser Network and visual acceptance (WEB-01)

The browser harness used temporary `playwright-core` tooling and did not add Playwright to application dependencies. Axios-adapter/Vitest mocks were **not** used as browser evidence. The original persistence/browser run passed at 13:19 UTC. A supplementary browser-only capture at **2026-11-05T13:45:09Z** preserved the request-level evidence missing from the original boolean summary; it added synthetic fixtures to the isolated test schema without dropping/resetting any database and did not repeat MySQL restart or BACKUP-01. Temporary storage and web processes were removed afterward.

Committed artifacts:

- [`browser-network.json`](evidence/v0.1/browser/browser-network.json): 99 ordered request/response events with methods, paths, statuses, and request/response linkage; inspected author-field allowlists; the 19-response business scan; stale-upload timeline; and zero operator audit requests. Only synthetic resource IDs and API paths are retained. Origins, query strings, headers, cookies, CSRF/session tokens, credentials, and request/response bodies are excluded.
- [`browser-result.json`](evidence/v0.1/browser/browser-result.json) and [`browser-run.log`](evidence/v0.1/browser/browser-run.log): passed assertion summary.
- [`acceptance.cjs`](evidence/v0.1/browser/acceptance.cjs): exact harness source used for the supplementary capture (SHA-256 `1498c205ad93159fe187433103eee729d653c19eca78e265b2b0b35d3028a238`).
- [`browser-authorized-download.pdf`](evidence/v0.1/browser/browser-authorized-download.pdf): 69-byte synthetic PDF used for the independent download-hash check.

With generated credentials and fixture variables already exported in the acceptance shell, the exact browser invocation was:

```bash
NODE_PATH=/tmp/asa-v01-browser-tool/node_modules node "$ROOT/docs/evidence/v0.1/browser/acceptance.cjs" > "$EVIDENCE/browser-run.log" 2>&1
```

Here `ROOT` was the documented project root, `EVIDENCE` was `$ROOT/docs/evidence/v0.1/browser`, `EVIDENCE_DIR` was exported with that same value, `FIXTURE_FILE=/tmp/asa-v01-browser-tool/evidence-fixture.json`, and `PDF_FIXTURE=$ROOT/backend/tests/fixtures/minimal.pdf`. Passwords remained in process environment variables and are absent from all committed artifacts.

An operator authorized only for the synthetic owner loaded a manuscript containing a coauthor with synthetic private email, phone, and notes markers. The linked request-level evidence proves:

- Response sequences **11** and **17** contain manuscript and immutable-snapshot author objects with exactly `author_id`, `display_name`, `position`, and `is_corresponding`; observed key sets and the allowlist are recorded explicitly.
- The operator's **19** business responses (sequences listed in `network_scan.response_sequences`) contain no synthetic private markers or `storage_path`/`stored_filename`: 18 JSON bodies were scanned, while response **37** is the separately hash-verified PDF. The rendered DOM also contained none of those markers or path fields.
- New-family upload response **21** returned **201**, file version 1. Existing-family upload response **29** returned **201**, file version 2 in the original family.
- Authorized download response **37** returned **200**; saved-file SHA-256 `453c8ccf889936826ae6e01dbda5cd2038f4a5b0c0aea9b3cb659efcd0e628cf` matches the uploaded second PDF.
- Competing version creation response **53** returned **201** while the second tab retained version 2. Stale upload request **64** produced exactly one response, **65**, with **409 `INVALID_MANUSCRIPT_STATE`**. The recorded timeline shows the request at 422 ms, conflict at 442 ms, non-retry warning and refresh action at 446 ms, and still exactly one upload POST when the explicit watch ended at 1449 ms (a 1000 ms watch after the conflict).
- Operator dashboard response **71** returned **200** and showed one authorized author. `operator_audit_request_sequences` is empty after navigating that operator to `/audit` and being redirected to dashboard.
- Administrator audit response **82** returned **200** with visible records. Auditor dashboard response **93** returned **403**, while auditor audit response **99** returned **200** with visible records.

The following actual screenshots from the supplementary run were opened and visually inspected: [`browser-manuscript.png`](evidence/v0.1/browser/browser-manuscript.png), [`browser-stale-409.png`](evidence/v0.1/browser/browser-stale-409.png), [`browser-dashboard-operator.png`](evidence/v0.1/browser/browser-dashboard-operator.png), [`browser-audit-admin.png`](evidence/v0.1/browser/browser-audit-admin.png), and [`browser-audit-auditor.png`](evidence/v0.1/browser/browser-audit-auditor.png). Pages, forms, files, conflict messaging, dashboard aggregates, and audit tables rendered with synthetic content; no sensitive markers or storage paths were visible. The manuscript screenshot also confirms the fixed snapshot authorship list shows one position marker per author. There is no browser-execution blocker to report.

## 5. Encrypted backup and isolated restore (BACKUP-01)

With application writers stopped, the proof used its protected `RESTORE_ADMIN_URL` provisioning path: `RESTORE_DATABASE_URL` was not used, the fixed empty `academic_submission_agent_restore_test` schema was created if absent and rejected if nonempty, and the existing `asa_test` identity received `ALL PRIVILEGES` on that restore schema only for the import. This did not assume or require preexisting `asa_test` privileges on the restore schema. The [`operations runbook`](operations.md#8-age-keys-encrypted-backup-and-isolated-restore) now documents both this protected path and a dedicated `asa_restore` alternative, with schema-scoped least-privilege provisioning. The real proof was executed:

```bash
.venv/bin/python scripts/test_backup_restore.py
```

Observed output (`backup-restore.log`):

- **19 tables after Alembic** (18 application tables plus migration bookkeeping).
- **9 source-table row-count comparisons**, excluding intentionally omitted sessions from dump comparison.
- **1 restored file** and **3/3 verified manifest hashes** (dump, configuration example, and storage file).
- `development_unchanged=true`, covering source row counts, table checksums, schema DDL hashes, and storage hashes.
- Age framing verified; no plaintext SQL/tar or `.partial` artifact remained; the temporary proof file and decrypted restore directory were removed.

Encrypted artifact: `academic-submission-agent-20261105T132015Z-168d47ff.tar.age`  
Encrypted artifact SHA-256: `03fe435da3c0c223d3f76cbcd7f54e0fbccae8451f81520b2b7a9fa29540e376`

The encrypted backup remains in Git-ignored `backups/`; its private age key was used only by the checked-in proof and was not read into evidence.

## 6. Safety and recovery checks

- `git ls-files` checks found no real `.env`, storage object, encrypted/plaintext backup, SQL dump, tar, or partial artifact tracked. No personal document was added.
- OpenAPI exposes only GET for `/api/v1/audit-logs` and `/api/v1/audit-logs/{log_id}`. Automated POST/PATCH/DELETE 405 and immutable-snapshot assertions also passed.
- Development and fixed test database names are distinct, the test host is loopback, and all destructive test/API commands used temporary non-live storage. Guard tests require explicit environment and host arguments.
- Unknown-commit preservation, reconciliation, orphan/missing handling, certain rollback compensation, stale-version races, and download-integrity blocking passed in the executable security matrix and full suite.
- Snapshot authorship now uses `authorship-position-list` to suppress the native ordered-list marker while retaining the stored position. A focused component/CSS regression passed, and the committed manuscript screenshot shows `1. Synthetic Evidence Owner` rather than `1. 1. ...`.
- `git diff --check` passed. The unrelated `.idea/AI Journal Submission Agent.iml` modification was left untouched and was not staged.

## 7. Residual limitations (not skipped gates)

1. **Development dependency audit is not clean.** Full `npm audit` reports five high-severity entries associated with CVE-2026-73231 in the Postman/Newman development dependency chain. Removing the redundant Faker override did not remove the required transitive dependency and did not break Newman. There is no supported Postman-compatible fixed release in the pinned toolchain. Production audit is clean at **0 vulnerabilities**.
2. V0.1 remains a loopback local deployment: no production TLS/reverse proxy, distributed login-rate limiting, malware-scanner integration, database-trigger immutability, or off-site age-key escrow is claimed. `scan_status=not_scanned` is not a malware-safety assertion.
3. Homebrew warns that the `mysql@8.0` formula is deprecated and scheduled for disablement on 2027-04-30. V0.1 intentionally targets MySQL 8.0; plan a reviewed database upgrade before that support boundary.

No required clean-install, migration, persistence, browser, isolation, file-recovery, coverage, OpenAPI/Newman, frontend-build, or BACKUP-01 gate was skipped or left failed.

## 8. Final-review fix wave verification

This section records the implementer's verification for the six final-review findings. It is **not** a clean final-review verdict; the scoped re-review remains required.

- Manuscript route reuse now reloads immediately on `manuscriptId` changes, invalidates stale sequences, clears the prior manuscript/version/file representation, and binds mutations to the loaded manuscript identity. In addition to the component regression, actual Google Chrome evidence delayed the m2 response, attempted a detached m1 authorship submission, and observed **zero authorship PUT requests**. See [`final-fix-route-reuse.cjs`](evidence/v0.1/browser/final-fix-route-reuse.cjs), [`browser-route-reuse-result.json`](evidence/v0.1/browser/browser-route-reuse-result.json), [`browser-route-reuse-loading.png`](evidence/v0.1/browser/browser-route-reuse-loading.png), and [`browser-route-reuse-second.png`](evidence/v0.1/browser/browser-route-reuse-second.png). The screenshots were visually inspected and contain only synthetic data.
- Permission and inactive-grant denials now commit one sanitized authorization-failure audit with the actor, author target, requested permission, request ID, and fixed error code. Expired, revoked, not-yet-active, role-denied, and active-grant-without-permission cases are covered; 404 behavior and sensitive-value exclusion remain covered. A reviewer+auditor regression proves that known and unknown UUIDs with no grant produce identical sanitized denial representations with `author_id` omitted in both, while grant-established denial paths retain the meaningful author ID.
- Formal publication uses a same-filesystem hard link followed by unlinking the temporary name. A deterministic destination-creation race proves existing bytes are neither overwritten nor removed by rollback compensation; certain and unknown outcome recovery tests remain green.
- The test client binds the global recovery engine to the isolated test engine. A canary checks the bind before issuing SQL and then proves the actual recovery session reports `academic_submission_agent_test`.
- Runtime request IDs require a string before trimming, with numeric, object, and null cases covered.
- Journal requirement verification timestamps require timezone awareness and are normalized to UTC before JSON storage and API response, with naive input and a non-UTC offset covered.

The complete `bash scripts/verify.sh` gate passed after these changes: **464 backend tests**, **126 frontend tests** (also repeated under coverage), **40/40 Newman requests and 97/97 assertions**, Ruff, mypy, OpenAPI generation/validation/diff, and the production build. Backend overall coverage is **95.71%**, permissions **98.78%**, file service **91.83%**, file validation **90.23%**, storage **94.83%**, services **93.54%**, and API **96.91%**. Frontend statement/branch/function/line coverage is **82.93% / 86.04% / 77.69% / 86.68%**.

Production `npm audit --omit=dev` remains clean at zero vulnerabilities. Full development `npm audit` still reports the five high-severity Faker/Postman advisory entries documented in section 7; this fix wave does not hide or claim to resolve them. The browser run used only the fixed `academic_submission_agent_test` schema and temporary storage, cleaned its synthetic records, and stopped both web processes. Development data, the root `.env`, existing age keys, and unrelated `.idea` changes were not touched.
