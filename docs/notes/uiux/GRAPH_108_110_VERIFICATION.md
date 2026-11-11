# Graph UI integration: issues #108 and #110

Local branch: `uiux-man/108-110-graph-fixes` in `D:/25125026_CS252/Group04-CS252-VirtualAssistant`.

This follow-up retains Thinh's #149 and #150 contributions. Both original PRs were merged into main under LePhanDucMan-pa before publishing these integration fixes for review.

## Implemented

- Canvas painting reads current zoom, pan, selection, hover and cycle state. Unpinned positions reset when changing layout; saved pins remain.
- Pointer capture supports node dragging, touch panning and pinch zoom. Selection happens after a click, not during dragging. Keyboard node controls focus/center a checkpoint.
- Edge hover displays metadata. Cycle validation uses the full graph even with filters active, prevents a client-side cycle request and renders the cycle in red. Structured server 409 paths are retained.
- Full/local graph responses normalize server field names, task statuses, CLO identifiers and source counts. Covers edges retain their server direction and metadata.
- Graph layout positions load/save through authenticated APIs, saves serialize, failures have a retry control, and old-course save responses cannot affect current-course status.
- Approved-roadmap edge controls add/remove through the existing APIs. Draft review retains its staged-edit behavior.
- CLO and verified-source filters use real graph metadata. Private uploads are excluded from the verified catalog-source count. Unknown source totals default to zero.
- List ordering honors prerequisites, including through hidden intermediate nodes. Search suggestions support keyboard selection. The node panel provides a local-graph action; closing it retains the center node.
- Query parameters restore filters, selected node, layout, view and roadmap without replacing the application route hash. Demo preview persistence remains session storage, explicitly separate from server persistence.
- Filter labels and duration hints meet contrast checks in the tested list/filter region. Axe is a development-only dependency.

## Verification

- `python dev.py devops ci`: 719 backend tests passed, Ruff passed, secret scan passed, benchmark fixtures validated. A pre-existing Windows checkout line-ending mismatch in `institutions.csv` was repaired locally to match Git exactly; it introduces no committed CSV change.

- `pnpm --dir ui exec vitest run --maxWorkers=2`: 194 tests passed across 36 files.
- `PLAYWRIGHT_CHANNEL=chrome pnpm --dir ui test:e2e`: 40 passed, 6 intentionally skipped. Skips cover desktop-only drag, mobile-only touch, and separately run opt-in benchmarks.
- Desktop/mobile browser checks cover search to panel, milestone coverage and prerequisites, CLO/verified filters, URL restoration after reload, local API calls, saved pinned positions, touch pinch, edge add/remove after reload, and scoped axe checks (no serious/critical violations).
- API browser checks use clearly identified intercepted fixtures. They verify UI/API contracts and reload state, not a production account or database. No backend code changed.
- Separate benchmark: 300 nodes, 299 prerequisite edges; week pan 50.5 FPS, force pan 54.4 FPS in local headless Chrome without CPU throttling. Force simulation pauses while background panning; canvas rendering continues each frame.
- Production build passes TypeScript and Vite. Main JS gzip: 120.20 KB versus 106.53 KB on `origin/main` with the same installed toolchain (+13.67 KB). CSS: 16.12 KB versus 13.64 KB. No runtime dependency added.

See `ui/README.md` for the benchmark command and existing run instructions.

## Remaining checks before closing issues

- Repeat the 300-node benchmark on a representative mid-range laptop; development-machine FPS is not proof of that hardware requirement.
- Deployed-backend/browser persistence still needs a smoke test. The local authenticated API persistence smoke passed against port 8000 (offline AI): graph/local graph reads, layout PUT/GET, edge POST/GET, cycle 409 with a path, and edge DELETE/GET. The synthetic course was retained for manual review; this does not test syllabus parser quality.
- Review the actual graph visually at desktop/mobile sizes. Figma was intentionally excluded at the user's request.
- Axe coverage here is limited to graph filters/list, not the whole application's accessibility.

PR #149 merged as `968d612`; PR #150 merged as `2c66ddc`. The older local issue #57/tutorial stash was left intact.

## Captured UI states

All screenshots use the explicit four-node API fixture, not production learner data.

![Week graph](graph-108-110/01-desktop-week.png)
![Blocked prerequisite cycle](graph-108-110/02-cycle-blocked.png)
![List](graph-108-110/03-desktop-list.png)
![CLO and verified-source filtering](graph-108-110/04-verified-clo-filter.png)
![Local graph](graph-108-110/06-local-graph.png)
![Mobile node panel](graph-108-110/08-mobile-node-panel.png)
