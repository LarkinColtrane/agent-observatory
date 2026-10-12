// Flat ESLint config assembled from the same rule sets eslint-config-next
// bundles (core JS, typescript-eslint, React, React Hooks, jsx-a11y), minus
// @next/eslint-plugin-next: that plugin depends on fast-glob -> micromatch ->
// braces, which carries an unpatched high-severity advisory
// (GHSA-vfj7-8cjw-p6xm). Coordinator decision: remove the chain rather than
// allowlist it (see ADR-0006).
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "coverage/**",
    "next-env.d.ts",
  ]),
  js.configs.recommended,
  tseslint.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    settings: { react: { version: "detect" } },
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
]);
