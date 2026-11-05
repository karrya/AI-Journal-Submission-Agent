# Encrypted backup and isolated restore

Backups contain a consistent MySQL dump, manuscript storage, `.env.example`, and a
SHA-256 manifest. The real `.env`, plaintext passwords, reusable cookies, and
`auth_sessions` contents are excluded. Restore recreates only that excluded table
from current model metadata, empty and without changing migration history, before
Alembic verification. Tar bytes are streamed directly into `age`; only an encrypted
`.tar.age` file is published, after its `.partial` file succeeds completely.

## Prerequisites

Stop the backend, frontend, workers, and every other application writer before the
backup and keep them stopped until verification finishes. Install `age`,
`mysqldump`, and `mysql`. Keep the dedicated private key outside this project and
Git. A key generated for this project normally lives at:

- `~/.config/academic-submission-agent/age/backup-key.txt`
- `~/.config/academic-submission-agent/age/recipient.txt`

Both files and their parent must be private to the operator. If a dedicated key
already exists, do not rotate or overwrite it. Provide its existing configuration
through the protected environment:

```bash
read -r AGE_RECIPIENT < ~/.config/academic-submission-agent/age/recipient.txt
export AGE_RECIPIENT
export AGE_SECRET_KEY_FILE="$HOME/.config/academic-submission-agent/age/backup-key.txt"
```

Never put the private key, recipient, database URL, or password in Git, command
arguments, logs, or this directory.

## Backup

With application writes stopped, run from the project root:

```bash
.venv/bin/python scripts/backup.py --confirm-writes-stopped
```

The default output is `backups/`. The database password is passed only to the
`mysqldump` subprocess as `MYSQL_PWD`. Any dump, tar, or age failure removes the
partial artifact and unencrypted temporary files.

## Isolated restore

Provision an **empty** database named `academic_submission_agent_restore_test` and
an account that can import and migrate only that database. Supply its URL through
`RESTORE_DATABASE_URL` in the protected environment. Use a dedicated account with
privileges on that database alone whenever possible. The restore target directory
must be new or empty and outside the actual configured `STORAGE_ROOT`; standalone
restore reads that root from the protected environment and rejects both the root
and every subdirectory.

```bash
.venv/bin/python scripts/restore.py \
  --backup backups/REPLACE_WITH_BACKUP.tar.age \
  --database academic_submission_agent_restore_test \
  --target-directory /tmp/academic-agent-restored-storage \
  --confirm RESTORE
```

The command rejects the development database, malformed or non-`_test` names,
non-empty targets, live-storage paths, unsafe archive members, and hash mismatches.
A MySQL-aware tokenizer accepts only expected mysqldump statement forms and exact
initialization/cleanup `SET` signatures; arbitrary SQL modes, user variables, and
parser-affecting statements are rejected. It rejects every schema-qualified
reference, including quoted, comment-split, and executable comment variants. The
import establishes `NO_AUTO_VALUE_ON_ZERO` itself, uses `mysql --one-database`, and
prepends only the validated isolated target `USE` statement after archive
validation.

The command compares dumped tables before migration, runs `alembic upgrade head`
and `alembic check`, compares all source row counts except excluded sessions,
verifies every manifest hash, and compares restored storage file names, counts,
and hashes. Sessions must remain empty. Standalone restore checks source table
names and row counts for stability; it does not claim content/schema immutability.
The real proof below additionally compares table checksums, schema DDL hashes, and
storage hashes before and after. Every decryption, restore, interruption, and
cleanup failure prevents success output and removes decrypted temporary data.

## Repeatable BACKUP-01 proof

The following performs one real backup and restore and removes the decrypted
restore directory afterward. It retains the encrypted backup in `backups/`:

```bash
.venv/bin/python scripts/test_backup_restore.py
```

By default the proof derives target credentials from `TEST_DATABASE_URL` and
requires the fixed restore database to exist already. Alternatively, set
`RESTORE_ADMIN_URL` in the protected environment. The proof then uses that
administrative connection only to create the fixed `_test` database if absent,
reject a non-empty one, and grant the existing test account access to it. It never
creates, grants on, imports into, or overwrites the development database.

When development storage is empty, the proof creates one exclusively named,
clearly labeled temporary text file so the real run verifies a non-zero storage
file count and hash. It refuses non-empty development storage, never overwrites an
existing path, removes only its own proof file, and removes a storage root only if
the proof created it. The encrypted backup retains the verified proof copy after
the development file is cleaned.
