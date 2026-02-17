import js from "@eslint/js";
import globals from "globals";
import { defineConfig } from "eslint/config";

// Symbols defined at top-level in one <script> and used in others.
// This project uses traditional script tags, not ES modules.
const projectGlobals = {
  // app.js — utility helpers
  copyToClipboard: "readonly",
  debounce: "readonly",
  escapeHtml: "readonly",
  escapeJs: "readonly",
  escapeRegex: "readonly",
  formatDate: "readonly",
  generateUniqueId: "readonly",
  reloadConfig: "readonly",
  setButtonLoading: "readonly",

  // api-client.js
  ApiClient: "readonly",

  // base-state.js
  baseState: "readonly",

  // session-manager.js
  getSessionId: "readonly",
  getStagingHeaders: "readonly",
  getUserIdentity: "readonly",
  hasUserIdentity: "readonly",
  setUserIdentity: "readonly",

  // ui-notifications.js
  showConfirmDialog: "readonly",
  showToast: "readonly",

  // git-ui.js
  closeGitResultOverlay: "readonly",
  closeGitResultPanel: "readonly",
  showGitOperationResult: "readonly",
  showGitRunningPanel: "readonly",

  // commit-dialog.js
  applyGitCommit: "readonly",
  applyGlobalCommit: "readonly",
  autoGitCommitGlobal: "readonly",
  closeGlobalCommitDialog: "readonly",
  discardGitChanges: "readonly",
  discardGlobalChanges: "readonly",
  discardStagingAfterFailedCommit: "readonly",
  handleCommitClick: "readonly",
  retryGitCommit: "readonly",
  showGitResultPanel: "readonly",
  showGlobalCommitDialog: "readonly",
  showResultPanel: "readonly",
  toggleReferencePreview: "readonly",
  updateGitOnlyContextLines: "readonly",
  updateGlobalContextLines: "readonly",

  // lock-manager.js
  breakLock: "readonly",
  checkLockStatus: "readonly",
  updateLockBannerUI: "readonly",

  // base.js
  DebugLogger: "readonly",
  pluralize: "readonly",
  showLoadingState: "readonly",
  updateNavCommitButton: "readonly",
  updateUndoButton: "readonly",
  withLoadingButton: "readonly",

  // shared/pagination.js
  renderPagination: "readonly",

  // explorer/main.js
  Explorer: "readonly",

  // docs-data.js
  NAGIOS_INHERITANCE_REFERENCE: "readonly",
  NAGIOS_OBJECT_REFERENCE: "readonly",

  // Template-injected globals (set in HTML <script> blocks)
  configPath: "readonly",
  configRootName: "readonly",

  // Callback hooks (defined in page scripts, called from core modules)
  buildTree: "readonly",
  onLockCleared: "readonly",
  renderTargetPane: "readonly",

  // explorer internal cross-file
  checkPendingChanges: "readonly",

  // External libraries loaded via CDN
  cytoscape: "readonly",

  // UMD module check (dependencies.js)
  module: "readonly",
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

      // --- Complexity ---
      "complexity": ["error", 20],

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
