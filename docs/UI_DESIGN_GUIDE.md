# UI design and maintenance

This refactor implements the reviewed Unslop/Astryx direction while retaining existing product wording. It preserves syllabus review and confirmation, roadmap approval, graph interactions and URL state, source provenance, personal library, scheduling, onboarding, and weekly feedback. It changes presentation and repeated controls, without changing API contracts.

## Where to edit

| Concern | Source |
| --- | --- |
| Cascade order | `ui/src/layers.css` |
| Shared Astryx provider and saved mode | `ui/src/features/appearance/StudyTheme.tsx` |
| Product surfaces, type, spacing and responsive navigation | `ui/src/features/appearance/study-ui.css` |
| Saved accent and Light/Dark/Windy/Flame/device behavior | `ui/src/features/appearance/appearance.ts` |
| All gradient preset IDs and color stops | `ui/src/features/appearance/gradients.ts` |
| Selected-gradient treatments and legacy demo compatibility | `ui/src/features/appearance/appearance.css` |
| Shared action wrapper | `ui/src/components/Button.tsx` |
| Graph disclosure, hidden-filter summary and clearing | `ui/src/components/GraphFilterBar.tsx` and `.css` |
| Four accessible review tabs | `ui/src/pages/course-setup/SyllabusReview.tsx` |

Astryx core, Neutral theme and CLI are pinned to **0.7.16**. Components use its published prebuilt CSS and theme; no custom StyleX compiler or runtime theme generator is required in application code. The two disabled package postinstall scripts only print setup guidance; they do not produce runtime artifacts.

## Style rules

The cascade order is `reset → study-legacy → astryx-base → astryx-theme → study-app`. Existing styles are inside `study-legacy`, so lazy-loaded screens cannot accidentally override migrated controls through broad `button` or `input` selectors. Put new product adaptations in `study-app`; keep feature-specific rules in their feature stylesheet. Preserve this order when adding imports.

Reading surfaces remain neutral in Light and Dark modes, and use frosted translucent surfaces (`rgba(255, 255, 255, 0.86)` over the `#86fde8 → #acb6e5` canvas in **Windy**; warm ivory `rgba(255, 251, 245, 0.90)` over the `#fdcf58 → #ff0000` canvas in **Flame**). The selected gradient remains visible on primary actions, active setup progress and navigation markers. Status colors retain their meanings. Account avatars stay neutral, and the existing brand markup is preserved. The retained old demo keeps its previous broader gradient treatment.

To add or update a gradient, edit the single `GRADIENTS` catalog. Retain existing IDs so saved choices remain valid. All stops feed the action and selection tokens; do not reduce a multicolor preset to its two endpoints. The dark veil on action fills protects white text over bright cyan/yellow stops. Review new palettes in both modes and keep the browser gradient/neutral-avatar regression passing.

Keep native controls where application constraints require them. For example, the course creation field retains native `required`, `maxLength` and disabled behavior. Astryx supplies the read-only course field, shared buttons, mobile menu icon button, icons and review tabs. The custom graph search, existing dialogs and node panel retain their established interactions and focus management.

## Graph controls

Search, milestone selection and graph/list choices stay visible. Remaining controls live in one disclosure with a normal advanced heading. The collapsed summary shows active hidden values. A changed week range counts once; local depth counts only as part of enabled local graph. Search, milestone and view choices do not inflate the hidden-filter count.

Clear resets filter values, including visible search/milestone, while retaining graph/list view. Layout and selected node are managed by the existing parent and remain intact. URL serialization still uses the existing `kg_*` fields.

## Verification

Run `pnpm exec vitest run --maxWorkers=2`, `pnpm run build`, and `pnpm exec playwright test` from `ui`. Run CPU-heavy unit and browser suites separately on constrained machines. Browser checks include keyboard-only review, citations, approval, graph URL reload, source/private-material access, scheduling, ownership, all five gradients in both modes, neutral avatars, compact mobile controls, and enlarged root text with Dark-mode contrast checks.

For the 300-node graph benchmark, run `GRAPH_PERFORMANCE=1` with the desktop browser project, `--grep "300-node" --repeat-each=3 --workers=1` (set the environment variable with PowerShell syntax on Windows). Do not run competing test suites while collecting samples.

The broader translation pass was deliberately deferred to honor the request to keep current text mostly unchanged. Automated accessibility and fixture checks do not replace a representative learner usability exercise.

## References and attribution

- [Astryx by Meta](https://github.com/meta/astryx), MIT. The implementation follows its published component, theme, CSS-layer and migration guidance.
- [Unslop by Damir Sokolovsky](https://github.com/heydamir/unslop), CC BY 4.0. Its audit approach informed the reduction of repeated gradients, decorative framing, excess spacing and control density; recommendations were adapted to preserve this app's established palettes and branding.
- `docs/APP_SPECIFICATION.md` remains the feature authority.
