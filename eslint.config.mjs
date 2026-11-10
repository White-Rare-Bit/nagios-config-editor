import js from "@eslint/js";
import globals from "globals";
import { defineConfig } from "eslint/config";

// Every file under app/static/js is an ES module, so imported names are in
// scope without declaring them here. Only names that are not imported belong
// in this list: values injected by templates and libraries loaded from a CDN.
const projectGlobals = {
  // Template-injected globals (set in HTML <script> blocks)
  configPath: "readonly",
  configRootName: "readonly",

  // External libraries loaded via CDN
  bootstrap: "readonly",
  cytoscape: "readonly",
};

export default defineConfig([
  {
    ignores: ["app/static/vendor/**"],
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    plugins: { js },
    extends: ["js/recommended"],
    languageOptions: {
      sourceType: "module",
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
