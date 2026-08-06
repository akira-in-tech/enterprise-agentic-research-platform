# Phase 12 Design QA

## Evidence

- Selected visual direction: `frontend/artifacts/reference-phase12.png`
- Implemented desktop viewport: `frontend/artifacts/home-desktop-viewport-phase12.png`
- Desktop full-page capture: `frontend/artifacts/home-desktop-phase12.png`
- Conclusion-first report capture: `frontend/artifacts/report-desktop-phase12.png`
- Responsive capture: `frontend/artifacts/home-mobile-phase12.png`
- Same-input visual comparison: `frontend/artifacts/comparison-phase12.png`
- QA URL state: development-only `?design-preview` fixtures with no backend mutation

## Capture normalization

- Source image: 1483 x 1061 pixels.
- Desktop browser override: 1488 x 1058 CSS pixels; captured viewport is 1473 x 1047 pixels after browser chrome and scrollbar allocation.
- Responsive browser override: 390 x 844 CSS pixels.
- Comparison input places the selected direction and matched desktop viewport side by side at equal rendered widths.

## Required fidelity surfaces

- Typography: passed. The restrained editorial serif headline and Inter interface type preserve the selected visual hierarchy without reducing body or status legibility.
- Spacing and first-screen rhythm: passed. Header, hero, composer, provider comparison, eight-agent flow, and all three recent-run states remain visible in the matched desktop viewport.
- Colors and tokens: passed. Warm ivory surfaces, charcoal text, moss accents, semantic statuses, focus rings, dark mode, and reduced motion use shared CSS tokens.
- Brand asset: passed. The selected charcoal rounded-square mark uses a real transparent PNG with a round eight-ray white star and green center. No copied logo, CSS drawing, inline SVG, emoji, or placeholder asset is used.
- Information architecture: passed. Reports show the conclusion first, research quality second, and evidence only after an explicit disclosure action.
- Product truthfulness: passed. Private knowledge stays visibly unavailable until the public request contract supports it; browser-local history is labeled as such.

## Complete state design

- Success: verified report with citation coverage and source count.
- Redis unavailable: request-not-started guidance and safe retry.
- SSE disconnected: durable-job explanation and reconnect action without implying job failure.
- Job failed: explicit stopped state and retry path.
- Report unavailable: completed-job preservation and report-only reload.
- Citation revision required: answer remains visible while verification is marked for review.

The development-only preview accepts `state=redis`, `state=sse`, `state=failed`, `state=report`, or `state=citation` with `design-preview` so these states can be reviewed without changing production behavior.

## Interaction and accessibility checks

- Provider selection exposes native radio semantics and a visible selected state.
- Workspace, theme, provider, submission, recent-run, retry, and evidence controls have keyboard focus treatment and at least 44-pixel primary targets.
- Running, completed, and failed states use text and icons rather than color alone.
- Evidence is collapsed by default to preserve report reading width, then exposed with `aria-expanded` and `aria-controls`.
- Desktop and 390-pixel responsive layouts were exercised in Chrome.
- The report fixture was opened from Recent research and Evidence was expanded through the real UI control.
- Browser console check returned no warnings or errors.
- Vue typecheck, 12 component/contract tests, and the Vite production build passed after the final visual refinement.

## Comparison history

### Pass 1

- P1: The desktop headline wrapped to five lines instead of four and pushed the workflow and recent research below the selected first-screen position.
- P2: The composer and provider rows were taller than the selected direction.

Fixes:

- Increased the desktop editorial column width and reduced the display type maximum from 70 to 60 pixels.
- Reduced hero gaps, composer textarea height, provider row height, and supporting-copy spacing.
- Re-captured the desktop viewport and rebuilt the side-by-side comparison.

### Pass 2

- No actionable P0, P1, or P2 mismatch remains.
- The selected charcoal eight-ray brand mark is an intentional replacement for the earlier visual-direction mark.
- The implemented provider comparison omits a deployment column to keep the real two-provider decision scannable at the supported width.
- The eight-agent workflow is intentionally compact: it shows orchestration progress without exposing internal state before the user asks for it.

## Follow-up polish

- P3: Connect the same tokens and components to a maintained Figma library if a collaborative design file becomes a project deliverable.
- P3: Replace browser-local Library data after a tenant-scoped history endpoint exists.

final result: passed
