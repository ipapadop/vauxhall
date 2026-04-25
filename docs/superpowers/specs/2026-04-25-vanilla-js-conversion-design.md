# Design: Vanilla JS Conversion for Dashboard Frontend

**Date:** 2026-04-25
**Status:** Approved
**Topic:** Converting the TypeScript UI to Vanilla JavaScript to remove the need for a frontend build step.

## 1. Overview
The frontend build infrastructure (Vite, `package.json`, `tsconfig.json`) was removed in a recent commit. This design outlines the steps to convert the remaining TypeScript (`.ts`) files in the UI to pure vanilla JavaScript (`.js`), allowing the browser to run them natively without any build step.

## 2. Architecture & Components

### 2.1 File Renaming & Cleanup
- Rename all `.ts` files to `.js` within `vauxhall/dashboard/ui/`:
  - `app.ts` -> `app.js`
  - `js/ipc.ts` -> `js/ipc.js`
  - `js/state.ts` -> `js/state.js`
  - `js/ui.ts` -> `js/ui.js`
- Delete `types.d.ts` as type definitions are no longer needed.

### 2.2 Code Conversion
- Remove all TypeScript-specific syntax from the `.js` files:
  - Remove type annotations (e.g., `: string`, `: number`, `: any`).
  - Remove interface and type declarations (e.g., `interface AgentState`, `type AgentStatus`).
  - Remove generic type parameters (e.g., `Map<string, AgentState>`).
  - Convert TypeScript enums to standard JavaScript objects or constants if any exist.
- Ensure all module imports/exports use standard ES6 syntax and explicitly include the `.js` extension (e.g., `import { setupIPC } from './js/ipc.js';`).

### 2.3 HTML & Python App Updates
- Update `vauxhall/dashboard/ui/index.html` to load the main script as an ES module:
  - `<script type="module" src="app.js"></script>`
- In `vauxhall/dashboard/app.py`, confirm that the application serves `vauxhall/dashboard/ui` correctly and does not strictly look for a `dist/` directory that no longer exists (it already falls back to `ui`, so it should be fine).

### 2.4 Documentation Updates
- Update `README.md` and `AGENTS.md`:
  - Remove mentions of `Node.js 18+` from the prerequisites.
  - Remove instructions to run `npm run build` after making frontend changes.
  - Update references from "TypeScript/Vite UI" to "Vanilla JS UI".

## 3. Testing Strategy
- Start the dashboard server (`python3 -m vauxhall.dashboard.app`).
- Open the dashboard in a web browser and verify that no JavaScript compilation errors appear in the console.
- Run the simulation script (`python3 scripts/simulate_agent.py -n 1 -t 5`) and confirm that the agent grid updates, the history modal functions, and the sorting mechanism still works.

## 4. Success Criteria
- [ ] The dashboard loads without any console errors related to unrecognized syntax.
- [ ] All `.ts` files have been removed or renamed to `.js`.
- [ ] No build step is required to run the frontend.
- [ ] Existing functionality (grid, modal, search, sorting) works correctly with Vanilla JS.