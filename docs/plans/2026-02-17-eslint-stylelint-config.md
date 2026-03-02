# ESLint + Stylelint Expert Configuration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Configure ESLint with full quality rules for JS, replace broken CSS linting with Stylelint, and fix all violations.

**Architecture:** ESLint for JS (sourceType "script" with project globals + 52 quality rules), Stylelint for CSS (stylelint-config-standard with project customizations). Two separate tools, each expert at their domain.

**Tech Stack:** ESLint 10, Stylelint 17, stylelint-config-standard 40

---

### Task 1: Update ESLint Config — Add All Quality Rules, Remove CSS

**Files:**
- Modify: `eslint.config.mjs`

**Step 1: Write the updated ESLint config**

Remove the `@eslint/css` import and CSS config block. Add all 52 quality rules to the existing rules section. Keep existing `projectGlobals`, `sourceType: "script"`, and tuned rules (`no-unused-vars`, `no-redeclare`, `no-empty`).

```javascript
import js from "@eslint/js";
import globals from "globals";
import { defineConfig } from "eslint/config";

// Symbols defined at top-level in one <script> and used in others.
// This project uses traditional script tags, not ES modules.
const projectGlobals = {
  // [KEEP EXISTING projectGlobals EXACTLY AS-IS]
};

export default defineConfig([
  {
    files: ["**/*.{js,mjs,cjs}"],
    plugins: { js },
    extends: ["js/recommended"],
    languageOptions: {
      sourceType: "script",
      globals: { ...globals.browser, ...projectGlobals },
    },
    rules: {
      // --- Existing tuned rules (keep) ---
      "no-unused-vars": ["error", {
        vars: "local",
        args: "after-used",
        argsIgnorePattern: "^_",
        caughtErrors: "none",
        destructuredArrayIgnorePattern: "^_",
      }],
      "no-redeclare": "off",
      "no-empty": ["error", { allowEmptyCatch: true }],

      // --- Bug prevention ---
      "curly": "error",
      "eqeqeq": ["error", "smart"],
      "radix": "error",
      "no-shadow": "error",
      "guard-for-in": "error",
      "consistent-return": "error",
      "array-callback-return": "error",
      "no-use-before-define": ["error", { functions: false }],
      "no-loop-func": "error",
      "no-self-compare": "error",
      "no-unmodified-loop-condition": "error",
      "no-unreachable-loop": "error",
      "no-template-curly-in-string": "error",
      "no-constructor-return": "error",
      "no-promise-executor-return": "error",

      // --- Dangerous patterns ---
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-caller": "error",
      "no-iterator": "error",
      "no-proto": "error",
      "no-extend-native": "error",
      "no-new-wrappers": "error",
      "no-multi-str": "error",
      "no-script-url": "error",
      "no-alert": "error",

      // --- Code quality ---
      "no-throw-literal": "error",
      "no-sequences": "error",
      "no-return-assign": "error",
      "no-nested-ternary": "error",
      "no-param-reassign": "error",
      "no-else-return": "error",
      "no-implicit-coercion": "error",
      "no-void": "error",
      "no-lonely-if": "error",
      "no-lone-blocks": "error",
      "no-new": "error",
      "no-label-var": "error",
      "dot-notation": "error",
      "default-case-last": "error",
      "default-param-last": "error",
      "grouped-accessor-pairs": "error",

      // --- Dead code / unnecessary code ---
      "no-extra-bind": "error",
      "no-useless-call": "error",
      "no-useless-concat": "error",
      "no-useless-return": "error",
      "no-unneeded-ternary": "error",
      "no-object-constructor": "error",
      "no-array-constructor": "error",
      "operator-assignment": "error",
      "prefer-regex-literals": "error",
      "prefer-promise-reject-errors": "error",
      "symbol-description": "error",
      "yoda": "error",
    },
  },
]);
```

**Step 2: Verify the config loads and shows expected violations**

Run: `npx eslint static/js/ 2>&1 | tail -1`
Expected: approximately 646 errors (71 existing + 575 new from quality rules)

**Step 3: Commit**

```bash
git add eslint.config.mjs
git commit -m "chore: add 52 ESLint quality rules, remove broken CSS linting"
```

---

### Task 2: Install Stylelint and Create Config

**Files:**
- Modify: `package.json`
- Create: `stylelint.config.mjs`

**Step 1: Install Stylelint packages**

Run: `npm install --save-dev stylelint stylelint-config-standard`
Run: `npm uninstall @eslint/css`

**Step 2: Create Stylelint config**

Create `stylelint.config.mjs`:

```javascript
/** @type {import('stylelint').Config} */
export default {
  extends: ["stylelint-config-standard"],
  rules: {
    // Enforce --nbe-* naming convention for custom properties
    "custom-property-pattern": [
      "^nbe-.+$",
      { message: "Custom properties must use --nbe-* prefix (e.g., --nbe-space-md)" }
    ],
    // Bootstrap compatibility — mixed class naming patterns
    "selector-class-pattern": null,
    // Bootstrap overrides require !important
    "declaration-no-important": null,
    // Fallback patterns use duplicate properties with different values
    "declaration-block-no-duplicate-properties": [true, {
      ignore: ["consecutive-duplicates-with-different-values"]
    }],
  },
};
```

**Step 3: Update package.json scripts**

```json
"scripts": {
  "lint": "npm run lint:js && npm run lint:css",
  "lint:js": "eslint static/js/",
  "lint:css": "stylelint 'static/css/**/*.css'"
}
```

**Step 4: Run Stylelint to see what it finds**

Run: `npx stylelint 'static/css/**/*.css' 2>&1 | tail -5`
Document the violation count and top categories.

**Step 5: Commit**

```bash
git add stylelint.config.mjs package.json package-lock.json
git commit -m "chore: add Stylelint for CSS linting, replace @eslint/css"
```

---

### Task 3: Auto-Fix ESLint Violations (517 fixes)

These rules support `--fix`: `curly` (490), `dot-notation` (10), `no-else-return` (10), `no-implicit-coercion` (7).

**Files:**
- Modify: all JS files in `static/js/` (auto-fix changes)

**Step 1: Run ESLint auto-fix**

Run: `npx eslint --fix static/js/ 2>&1 | tail -1`
Expected: error count drops by ~517 (from ~646 to ~129)

**Step 2: Spot-check the auto-fixes look correct**

Run: `git diff --stat` to see which files changed.
Run: `git diff static/js/api-client.js | head -40` to verify curly braces were added correctly.

**Step 3: Run Python tests to verify nothing broke**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass

**Step 4: Commit**

```bash
git add static/js/
git commit -m "fix: auto-fix 517 ESLint violations (curly, dot-notation, no-else-return, no-implicit-coercion)"
```

---

### Task 4: Manual Fix — radix Violations (22 fixes)

Every `parseInt(x)` needs `parseInt(x, 10)`.

**Files:**
- Modify: files reported by `npx eslint --rule '{"radix": "error"}' static/js/ 2>&1 | grep radix`

**Step 1: Find all violations**

Run: `npx eslint static/js/ 2>&1 | grep radix`
List every file:line.

**Step 2: Fix each parseInt call**

Add `, 10` as the second argument to every `parseInt()` call. Example:
- Before: `parseInt(value)`
- After: `parseInt(value, 10)`

**Step 3: Verify fixes**

Run: `npx eslint --rule '{"radix": "error"}' static/js/ 2>&1 | grep radix`
Expected: no radix violations

**Step 4: Commit**

```bash
git add static/js/
git commit -m "fix: add radix parameter to all parseInt calls"
```

---

### Task 5: Manual Fix — no-nested-ternary Violations (15 fixes)

Refactor nested ternaries into if/else blocks or separate variables.

**Files:**
- Modify: files reported by `npx eslint static/js/ 2>&1 | grep no-nested-ternary`

**Step 1: Find all violations**

Run: `npx eslint static/js/ 2>&1 | grep no-nested-ternary`

**Step 2: Refactor each nested ternary**

For each violation, read the surrounding code and refactor. Common patterns:
- `a ? b ? c : d : e` → extract into if/else or separate `const`
- Deeply nested → use early returns or a lookup object

**Step 3: Verify fixes**

Run: `npx eslint static/js/ 2>&1 | grep no-nested-ternary`
Expected: no nested-ternary violations

**Step 4: Commit**

```bash
git add static/js/
git commit -m "fix: refactor 15 nested ternary expressions into readable conditionals"
```

---

### Task 6: Manual Fix — Remaining JS Violations (~21 fixes)

**Rules:** no-param-reassign (7), no-shadow (6), no-void (3), guard-for-in (2), no-lonely-if (2), consistent-return (1)

**Files:**
- Modify: files reported by `npx eslint static/js/ 2>&1 | grep -E 'no-param-reassign|no-shadow|no-void|guard-for-in|no-lonely-if|consistent-return'`

**Step 1: Find all violations**

Run: `npx eslint static/js/ 2>&1 | grep -E 'no-param-reassign|no-shadow|no-void|guard-for-in|no-lonely-if|consistent-return'`

**Step 2: Fix each violation**

- **no-param-reassign (7):** Create a local variable instead of reassigning the parameter. `function f(x) { x = ...; }` → `function f(x) { let val = ...; }`
- **no-shadow (6):** Rename the inner variable to avoid shadowing. Read both scopes to pick a clear name.
- **no-void (3):** Replace `void 0` with `undefined`, or restructure the expression.
- **guard-for-in (2):** Wrap the body in `if (Object.hasOwn(obj, key))` or switch to `Object.keys().forEach()`.
- **no-lonely-if (2):** Convert `else { if (x) { ... } }` to `else if (x) { ... }`.
- **consistent-return (1):** Ensure the function either always returns a value or never does.

**Step 3: Verify fixes**

Run: `npx eslint static/js/ 2>&1 | grep -E 'no-param-reassign|no-shadow|no-void|guard-for-in|no-lonely-if|consistent-return'`
Expected: no violations for these rules

**Step 4: Commit**

```bash
git add static/js/
git commit -m "fix: resolve remaining ESLint quality violations (shadow, param-reassign, guard-for-in, void, lonely-if, consistent-return)"
```

---

### Task 7: Assess and Fix Stylelint CSS Violations

**Files:**
- Modify: CSS files in `static/css/`

**Step 1: Run Stylelint and categorize violations**

Run: `npx stylelint 'static/css/**/*.css' 2>&1`
Group violations by rule. Assess each category: is it a real issue, or does the Stylelint config need further tuning?

**Step 2: Tune Stylelint config if needed**

If violations are false positives for this project's patterns, update `stylelint.config.mjs` to disable or configure those rules. Common adjustments:
- `function-no-unknown`: null (if modern CSS functions like `color-mix()` are flagged)
- `at-rule-no-unknown`: null (if custom at-rules are flagged)
- `property-no-vendor-prefix`: null (if vendor prefixes are needed)

**Step 3: Auto-fix what Stylelint can fix**

Run: `npx stylelint 'static/css/**/*.css' --fix 2>&1 | tail -5`

**Step 4: Manual-fix remaining CSS violations**

Read each violation, fix in the CSS file.

**Step 5: Verify clean**

Run: `npx stylelint 'static/css/**/*.css' 2>&1 | tail -1`
Expected: no violations (or only known exceptions)

**Step 6: Commit**

```bash
git add static/css/ stylelint.config.mjs
git commit -m "fix: resolve Stylelint CSS violations, tune config for project patterns"
```

---

### Task 8: Final Verification

**Step 1: Run full lint**

Run: `npm run lint`
Expected: Only the 71 pre-existing `no-unused-vars` / `no-undef` / `no-case-declarations` / `no-useless-assignment` / `no-useless-escape` / `no-prototype-builtins` / `no-control-regex` errors remain. Zero new violations from quality rules. Zero CSS violations.

**Step 2: Run Python tests**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass

**Step 3: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "chore: finalize ESLint + Stylelint configuration"
```
