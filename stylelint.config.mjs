/** @type {import('stylelint').Config} */
export default {
  extends: ["stylelint-config-standard"],
  rules: {
    // Allow --nbe-*, --color-*, --bs-* custom property prefixes
    "custom-property-pattern": [
      "^(nbe|color|bs)-.+$",
      { message: "Custom properties must use --nbe-*, --color-*, or --bs-* prefix" }
    ],
    // Bootstrap compatibility — mixed class naming patterns
    "selector-class-pattern": null,
    // Bootstrap overrides require !important
    "declaration-no-important": null,
    // Fallback patterns use duplicate properties with different values
    "declaration-block-no-duplicate-properties": [true, {
      ignore: ["consecutive-duplicates-with-different-values"]
    }],
    // Component CSS files have intentional specificity ordering
    "no-descending-specificity": null,
    // IDs use camelCase from JavaScript DOM references
    "selector-id-pattern": null,
    // Project uses custom keyframe names
    "keyframes-name-pattern": null,
    // Vendor prefixes still needed for browser compatibility
    "property-no-vendor-prefix": null,
    // Compact utility classes use single-line multi-declarations
    "declaration-block-single-line-max-declarations": null,
    // Large component files organize selectors by section, not uniqueness
    "no-duplicate-selectors": null,
  },
};
