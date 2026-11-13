# 02 · Requirements and environment configuration

| File | Purpose |
|---|---|
| `requirements.txt` | Backend Python dependencies, every package pinned to an exact version |
| `requirements-dev.txt` | Kept for compatibility; it only includes `requirements.txt` (test and lint tools are already in it) |
| `frontend-package.json` | Frontend dependencies (copy of `frontend/package.json`) |
| `frontend-package-lock.json` | Exact resolved frontend dependency tree, used by `npm ci` |
| `backend.env.example` | Backend configuration template; copy to `backend/.env` |
| `frontend.env.example` | Frontend configuration template; copy to `frontend/.env` |

## Runtime versions used for verification

- Python 3.11.18
- Node.js 24.18.0, npm 11.16.0 (the project requires Node.js 20 or newer)

## How the dependencies were verified

1. **Pins match the tested environment.** Each of the 19 pinned packages in `requirements.txt` was compared with the
   version installed in the development virtual environment: no mismatches. `pip check` reported no broken requirements.
2. **Fresh install.** The submitted source tree (`01_source_code/MindBridge`) was copied to an empty directory, a new
   virtual environment was created, and `pip install -r requirements.txt` and `npm ci` were run from scratch. The backend
   test suite, the five exam scenarios and the frontend production build were then run on that fresh copy. The results
   are recorded in `07_test_cases/fresh_install_verification.txt`.

## Secrets

The example files contain placeholders only (`your-gemini-api-key-here`, `your-langsmith-api-key-here`). The real
`backend/.env` is excluded from the submission. The backend treats the placeholder values as "not set", so the app
starts without any key; the five exam scenarios run offline with a deterministic scripted model.
