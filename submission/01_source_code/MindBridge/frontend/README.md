# MindBridge frontend

React 19 + TypeScript + Tailwind CSS 4, built with Vite. It talks to the FastAPI backend only through the typed
client in `src/api/client.ts`; `src/types/api.ts` mirrors the backend's Pydantic schemas.

```bash
npm install
cp .env.example .env      # VITE_API_BASE_URL=http://localhost:8000
npm run dev               # http://localhost:5173
npm run build             # type-check (tsc -b) and production build into dist/
npm run lint              # oxlint
```

| Path | Contents |
|---|---|
| `src/App.tsx` | App shell: home, patient check-in and clinician review |
| `src/components/Home.tsx` | What MindBridge is, the three stages, entry points |
| `src/components/TopBar.tsx` | Header with the stage navigation; AI assistant settings (clinician workspace only) |
| `src/components/PatientWorkspace.tsx`, `patient/` | Guided check-in: conversation, progress rail, quick replies, saved check-ins, confirmation |
| `src/components/ClinicianWorkspace.tsx`, `clinician/` | Review queue, case overview, review areas, answers to double-check, answers by topic, missing information, sign-off |
| `src/components/CrisisBanner.tsx` | Fixed crisis contacts shown when a safety concern is disclosed |
| `src/lib/` | Topic metadata, formatting, risk grouping, quick-reply detection, style helpers |

See the project README for the full setup, including the one-command `start.sh` / `start.bat`.
