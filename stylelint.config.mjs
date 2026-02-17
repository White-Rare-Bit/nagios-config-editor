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
