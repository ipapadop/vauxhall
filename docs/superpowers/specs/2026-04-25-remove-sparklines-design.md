# Design: Remove SVG Sparklines from Dashboard

**Date:** 2026-04-25
**Status:** Approved
**Topic:** Removing the token usage trend sparklines from the agent cards.

## 1. Overview
The sparkline feature (SVG trend lines for token usage) is being removed to simplify the UI and reduce technical debt. This involves removing the SVG elements from the frontend template, the logic for generating the sparkline paths, and the associated state management for token history.

## 2. Architecture & Components

### 2.1 Frontend Logic (`vauxhall/dashboard/ui/js/ui.js`)
- **Removal**: Delete the `generateSparklinePath` function.
- **Template Update**: Remove the `<div class="stats-row">` containing the `<svg class="sparkline">` from the `createCard` function's `innerHTML` template.
- **Update Logic**: Remove the code in `updateCard` that selects the polyline and sets its `points` attribute.
- **Import Cleanup**: Remove the import of `updateTokenHistory` from `./state.js`.

### 2.2 Frontend State (`vauxhall/dashboard/ui/js/state.js`)
- **Removal**: Delete the `updateTokenHistory` function.
- **Cleanup**: Ensure no references to `card.tokenHistory` remain.

### 2.3 Frontend Styles (`vauxhall/dashboard/ui/style.css`)
- **Removal**: Delete the CSS rules for `.sparkline` and `.sparkline polyline`.

## 3. Data Flow
The data flow for `tokens` will still update the `metric-badge` in the card footer, but it will no longer be pushed to a `tokenHistory` array or used to re-render an SVG.

## 4. Testing Strategy
- **Manual Verification**: Launch the dashboard and verify that agent cards no longer contain the sparkline SVG and that the layout remains consistent.
- **Console Check**: Verify that no JavaScript errors are thrown due to missing functions or null references (e.g., trying to find the sparkline element).
- **Python Tests**: Run `pytest` to ensure that no backend telemetry logic was accidentally affected (though changes are restricted to the frontend).

## 5. Success Criteria
- [ ] Sparkline SVGs are gone from the dashboard UI.
- [ ] `vauxhall/dashboard/ui/js/ui.js` no longer imports `updateTokenHistory`.
- [ ] `generateSparklinePath` and `updateTokenHistory` are deleted.
- [ ] All documentation references to sparklines are removed.
