# V0.1 final acceptance

**Acceptance date:** 2026-11-05 (evidence timestamp 2026-11-05T13:22:15Z)  
**Result:** **PASS — all required V0.1 gates executed successfully.** The residual limitations below do not represent skipped or failed required gates.

The tested change is based on commit `fddff14` plus the Task 18 documentation and reviewed minor hardening changes. The Task 18 report records the implementation and verification scope. No real password, database URL, session token, age private key, personal document, or server storage path is included here.

## Environment

- macOS on arm64; Homebrew `mysql@8.0` 8.0.46 (final runtime), Python 3.13.3, Node 26.13.0, npm 11.20.0.
- Backend: `/Users/didi/PycharmProjects/AI Journal Submission Agent/.venv/bin/python`.
- Browser: actual Google Chrome 156.0.8078.80, headless, driven by temporary `playwright-core` tooling outside the application dependencies.
- Raw logs, non-secret snapshots, and synthetic-data screenshots are under `.superpowers/sdd/2026-11-04-v0-1-implementation/acceptance/`; that workspace is not a release artifact and is not committed.

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

`bash scripts/verify.sh` passed after clean installation and again on the final repaired MySQL runtime (`verify-clean.log`, `verify-final-pre-doc.log`).

| Gate | Result |
|---|---|
| Ruff and mypy | Passed; all checks clean |
| Backend pytest | **458 passed**, 0 failed (latest final run 27.78 s) |
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
| Frontend unit tests | **22 files, 121 tests passed**, repeated for the coverage run |
| Frontend statement coverage | **82.66%** (1645/1990) |
| Frontend branch coverage | **85.84%** (1946/2267) |
| Frontend function coverage | **77.61%** (437/563) |
| Frontend line coverage | **86.52%** (1516/1752) |
| Frontend production build | `vue-tsc --noEmit && vite build` passed; latest final Vite build completed in 2.07 s |

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

The browser harness used `/tmp/asa-v01-browser-tool` and did not add Playwright to application dependencies. Axios-adapter/Vitest mocks were **not** used as browser evidence. The run captured actual Chrome responses and rendered screenshots; `browser-result.json` records `status=passed`.

An operator authorized only for the owner loaded a manuscript containing a coauthor with synthetic private email, phone, and notes markers. Results:

- Manuscript and immutable snapshot author objects contained exactly `author_id`, `display_name`, `position`, and `is_corresponding`.
- Nineteen captured business Network responses contained none of the synthetic private markers and no `storage_path` or `stored_filename`. The rendered DOM also contained none of those markers or path fields.
- New-family upload returned **201**, file version 1. Existing-family upload returned **201**, file version 2 in the original family.
- Authorized browser download returned **200**; saved-file SHA-256 was `453c8ccf889936826ae6e01dbda5cd2038f4a5b0c0aea9b3cb659efcd0e628cf`, matching the uploaded second PDF.
- A second tab retained stale version 2 while the first tab created version 3. Its upload returned **409 `INVALID_MANUSCRIPT_STATE`**. Exactly **one** upload POST was observed, including after a one-second retry watch; the UI displayed that the upload was not retried and offered explicit refresh.
- Operator dashboard returned **200** and showed one authorized author. Navigating that operator to `/audit` redirected to dashboard with **zero audit API requests**.
- Administrator audit returned **200** with visible records. Auditor dashboard returned **403**, while auditor audit returned **200** with visible records.

The following actual screenshots were opened and visually inspected after the run: `browser-manuscript.png`, `browser-stale-409.png`, `browser-dashboard-operator.png`, `browser-audit-admin.png`, and `browser-audit-auditor.png`. Pages, forms, files, conflict messaging, dashboard aggregates, and audit tables rendered with content; no sensitive markers or storage paths were visible. There is no browser-execution blocker to report.

## 5. Encrypted backup and isolated restore (BACKUP-01)

With application writers stopped, an empty `academic_submission_agent_restore_test` was prepared using the existing test-scoped account. The real proof was executed:

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
- `git diff --check` passed. The unrelated `.idea/AI Journal Submission Agent.iml` modification was left untouched and was not staged.

## 7. Residual limitations (not skipped gates)

1. **Development dependency audit is not clean.** Full `npm audit` reports five high-severity entries associated with CVE-2026-73231 in the Postman/Newman development dependency chain. Removing the redundant Faker override did not remove the required transitive dependency and did not break Newman. There is no supported Postman-compatible fixed release in the pinned toolchain. Production audit is clean at **0 vulnerabilities**.
2. V0.1 remains a loopback local deployment: no production TLS/reverse proxy, distributed login-rate limiting, malware-scanner integration, database-trigger immutability, or off-site age-key escrow is claimed. `scan_status=not_scanned` is not a malware-safety assertion.
3. Snapshot authorship lists visually combine the HTML ordered-list marker with the stored author position (for example, `1. 1.`). This is a cosmetic presentation issue only; stored positions, Network payloads, and authorization checks were correct.
4. Homebrew warns that the `mysql@8.0` formula is deprecated and scheduled for disablement on 2027-04-30. V0.1 intentionally targets MySQL 8.0; plan a reviewed database upgrade before that support boundary.

No required clean-install, migration, persistence, browser, isolation, file-recovery, coverage, OpenAPI/Newman, frontend-build, or BACKUP-01 gate was skipped or left failed.
