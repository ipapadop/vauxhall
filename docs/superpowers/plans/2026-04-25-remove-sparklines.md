# Remove SVG Sparklines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the token usage trend sparklines from the agent cards and clean up associated code.

**Architecture:** We will surgically remove SVG elements from the UI template, delete the sparkline generation logic, purge token history from the state management, and update documentation.

**Tech Stack:** Vanilla JavaScript, CSS, Markdown.

---

### Task 1: Cleanup Frontend Logic and State

**Files:**
- Modify: `vauxhall/dashboard/ui/js/ui.js`
- Modify: `vauxhall/dashboard/ui/js/state.js`

- [ ] **Step 1: Remove `generateSparklinePath` and related logic from `ui.js`**

```javascript
// vauxhall/dashboard/ui/js/ui.js

// Remove import
import { updateTokenHistory } from './state.js';

// Delete function generateSparklinePath
export function generateSparklinePath(history) { ... }

// Update createCard template: remove <div class="stats-row"> containing the sparkline
// Update updateCard logic: remove sparkline update code
```

- [ ] **Step 2: Remove `updateTokenHistory` and state cleanup from `state.js`**

```javascript
// vauxhall/dashboard/ui/js/state.js

// Delete function updateTokenHistory
export function updateTokenHistory(card, tokens) { ... }
```

- [ ] **Step 3: Commit code cleanup**

```bash
git add vauxhall/dashboard/ui/js/ui.js vauxhall/dashboard/ui/js/state.js
git commit -m "refactor: remove sparkline logic and token history state"
```

### Task 2: Cleanup Styles and Template

**Files:**
- Modify: `vauxhall/dashboard/ui/style.css`
- Modify: `vauxhall/dashboard/ui/js/ui.js`

- [ ] **Step 1: Remove sparkline CSS rules**

```css
/* vauxhall/dashboard/ui/style.css */

/* Remove .sparkline and .sparkline polyline rules */
```

- [ ] **Step 2: Verify `createCard` template removal in `ui.js`**

Ensure `<div class="stats-row">` is completely removed.

- [ ] **Step 3: Commit style cleanup**

```bash
git add vauxhall/dashboard/ui/style.css vauxhall/dashboard/ui/js/ui.js
git commit -m "style: remove sparkline CSS and UI template elements"
```

### Task 3: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Remove sparkline mentions from README.md**

```bash
sed -i '/SVG Sparklines/d' README.md
```

- [ ] **Step 2: Remove sparkline mentions from AGENTS.md**

```bash
sed -i '/Sparklines/d' AGENTS.md
sed -i '/SVG Sparkline in the card body/d' AGENTS.md
```

- [ ] **Step 3: Commit documentation updates**

```bash
git add README.md AGENTS.md
git commit -m "docs: remove references to SVG sparklines"
```
