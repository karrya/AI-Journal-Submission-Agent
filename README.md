# AI-Journal-Submission-Agent

## Local development

The selected local installation uses **Homebrew MySQL**, not Docker. Copy `.env.example` to `.env`, fill in the local credentials and CSRF secret, and run the existing MySQL bootstrap process before starting the application.

```bash
bash scripts/dev_backend.sh
bash scripts/dev_frontend.sh
```

The backend listens on `127.0.0.1:8000`; open the frontend at `http://localhost:5173`.

Run every backend, contract, frontend, coverage, and production-build gate with:

```bash
bash scripts/verify.sh
```

`docker-compose.yml` is optional and defines only MySQL 8 with a private named volume and no published port, so it does not conflict with Homebrew MySQL. Set `MYSQL_ROOT_PASSWORD` explicitly if you choose to use it; do not start both installations against the same data.
