# Pathly UI

The web frontend of the CS252 study assistant: React, TypeScript and Vite. It turns a course syllabus into a week-by-week roadmap, then into study sessions on a calendar. The interface is in Vietnamese.

It runs in two modes, chosen at build time by `VITE_BACKEND_MODE`:

| Mode | How | What works |
| --- | --- | --- |
| Preview (default) | no variable, or `VITE_BACKEND_MODE=demo` | The whole core loop in the browser with no server: upload or paste a syllabus (PDF, DOCX or text, parsed by simple rules in `src/api/demoParser.ts`), review it, get a roadmap, approve it, see sample sessions. Nothing is sent anywhere; the course lives in this tab's `sessionStorage`. |
| Full app | `VITE_BACKEND_MODE=api` | Sign-in, AI syllabus parsing, saved roadmaps, learning sources per step, lecture uploads and concepts, the real calendar with check-in and replanning, the study companion, and the admin screens. Needs the backend at `VITE_API_URL` (default `http://127.0.0.1:8000`). |

The preview is what GitHub Pages serves (`.github/workflows/pages.yml`).

## Run it

Requirements: Node.js 24 LTS. From the repo root:

```bash
python dev.py ui install
python dev.py ui dev
```

or from this folder: `npm install` then `npm run dev`. Open the printed URL, normally `http://127.0.0.1:5173`. On Windows, `start.cmd` starts the dev server without needing a PowerShell execution policy change.

For the full app, start the backend first, then set the mode (copy `check-config.example` to `.env.local`, or set the variable in the shell) and restart Vite:

```powershell
.\.venv\Scripts\python.exe -m uvicorn assistant.backend.main:app --app-dir src --port 8000
$env:VITE_BACKEND_MODE="api"; python dev.py ui dev
```

## Screens

Hash routes, so a link or a reload opens the same screen and a static host needs no rewrites.

- `#course` Môn học: the three-step setup (syllabus in, review, approve the proposed roadmap), then the course overview: progress, what is next, the next milestone.
- `#roadmap` Lộ trình: the roadmap as a route (one line, a stop per step, a diamond per milestone) or as a prerequisite graph. Selecting a step opens its panel: prerequisites (editable; a link that would close a loop is refused), and in the full app its sources, most trusted first: your own pages, catalog sources that passed review, then web results you can rate or search again.
- `#schedule` Lịch học: sessions by day with check-in, free and busy time, and replanning with a preview before anything is saved.
- `#library` Tài liệu: lecture uploads, the concepts found in them, cited practice questions (full app only).
- `#admin` Quản trị: catalog review queue (J/K to move, V to verify, R to reject), catalog health, search costs. Shown only to admins; the server enforces it.

## Code map

- `src/App.tsx`: the auth gate and the workspace (current user, notifications, side panels).
- `src/app/`: `useCourse.ts` (the one course and every step of its core loop), `routes.ts`, `Shell.tsx` (rail on wide screens, top bar and tab bar on phones), `theme.ts`, `text.ts` (Vietnamese labels, dates, error sentences).
- `src/screens/`: one file per screen; `setup/` holds the upload and review steps, `roadmap/` the route timeline, the graph, the step panel and the source card.
- `src/ui/`: `kit.tsx` (Button, Field, Dialog, Drawer, Tabs, Notice, …) and `icons.tsx`.
- `src/styles/`: `base.css` (design tokens with `light-dark()`, primitives) and `screens.css` (screen layouts).
- `src/api/`: every backend call and the wire types; `contract.test.ts` fails when the types drift from `docs/openapi.json`. `mockCore.ts` and `demoParser.ts` are the preview's stand-ins.

## Design

One typeface (Be Vietnam Pro, bundled). Colour carries meaning only: pine is the learner's route and progress, marigold is a milestone or something that needs attention, brick is a failure. The recurring figure is the route line, used for the setup steps, the roadmap, the day's sessions and the sign-in screen. Light and dark themes follow the device unless the learner picks one in Cài đặt. Motion only answers an action (a panel opening, a dialog rising) and is removed under `prefers-reduced-motion`.

## Checks

```bash
npm test            # unit tests (vitest)
npm run build       # type-check and production build
npm run test:e2e    # browser tests (Playwright)
```

The browser tests start their own dev servers on ports 5178 (preview) and 5180 (full app with intercepted API responses), on desktop and phone viewports, and scan each screen with axe. The full-app tests check the UI against fixture responses; they do not prove the server. If the bundled Chromium hangs on your machine, use installed Chrome: `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e`.

## Known limits

- The graph has no zoom or minimap; it scrolls. Fine for a semester-sized roadmap, cramped beyond about 30 steps.
- Step status (done, in progress) is read when the roadmap opens; it does not refresh after a check-in until the page reloads.
- Concept edits in Tài liệu are not saved to the server yet.
- The app handles one course at a time and reopens the last approved roadmap from this browser.
