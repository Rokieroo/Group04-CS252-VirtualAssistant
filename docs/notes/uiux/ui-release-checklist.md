# Pathly UI release checklist

Last reviewed: 2026-10-24

This file records the checks that should be completed before the Pathly UI branch is pushed and a pull request is opened.

## Current verification status

- Node.js 24.22.1 LTS is installed and satisfies the UI engine requirement.
- The TypeScript and Vite production build passes.
- All 5 state-model tests pass.
- All 4 existing Python assistant tests pass in the project-local `.venv`.
- The production dependency audit reports no known vulnerabilities.
- The complete development dependency audit reports no known vulnerabilities after upgrading Vitest to 4.1.12.
- The repository scan found no credentials or private keys.
- `ui/node_modules/` and `ui/dist/` are ignored and must not be committed.
- Local `main` matched `origin/main` at commit `edc5f3f` when this checklist was created.
- Browser regression checks passed for Home, week/month Schedule, Library, enrollment, per-course Progress, milestone routing, and navigation scroll reset.
- The browser console reported no warnings or errors during the regression pass.

## Required before push

- [x] Upgrade Vitest to version 4.1.12 or newer.
- [x] Regenerate `ui/pnpm-lock.yaml` with the selected dependency version.
- [x] Run `pnpm audit` and confirm that the development dependency findings are resolved.
- [x] Run `pnpm test` and confirm that every test passes.
- [x] Run `pnpm run build` and confirm that the production build succeeds.
- [x] Review `git status --short` and confirm that generated folders remain ignored.
- [ ] Create a feature branch rather than committing the UI directly to `main`.
- [ ] Review the staged diff before committing.

## Resolved dependency finding

The initial audit on 2026-10-24 reported two critical and three moderate findings in development-only test tooling:

- `tinypool`, included through Vitest, reported prototype-pollution-to-code-execution advisories. The audit requires `tinypool` 2.1.2 or newer.
- `vitest` and `@vitest/mocker` reported path-traversal and manual-mock code-injection advisories. The audit requires Vitest 4.1.12 or newer.

These packages are not included in the deployed static website. Vitest was upgraded from 3.2.7 to 4.1.12 and the lockfile was regenerated. Both `pnpm audit` and `pnpm audit --prod` now report no known vulnerabilities.

## Suggested branch and commit

```bash
git switch -c codex/pathly-ui
git add README.md docs ui
git commit -m "feat(ui): add Pathly interactive frontend"
git push -u origin codex/pathly-ui
```

Do not run the commit or push commands until every required checkbox above has been completed.

## Pull request notes

Include these points in the pull request description after the checklist is complete:

- Adds the React and TypeScript Pathly interface.
- Adds responsive Home, Schedule, Progress, Library, and AI Reporter screens.
- Adds local demo persistence and date migration.
- Adds Windows launchers and end-user installation instructions.
- Records the Node.js 24 LTS requirement.
- Confirms tests, production build, and full dependency audit results.
