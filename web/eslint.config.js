// Lint the hook rules (F-046): rules-of-hooks and exhaustive-deps catch the main bug class here (a
// stale value after a refetch). Every switch-off must say why ("-- reason"), and a switch-off that
// no longer hides anything fails the run. Lines stay under 300 characters (F-034).
// ponytail: 300 stops the worst lines without reformatting the dense house style; a lower limit
// (or Prettier, ~+13k lines) is a separate decision.
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "test-results/**", "playwright-report/**"] },
  {
    files: ["src/**/*.{ts,tsx}", "e2e/**/*.ts"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "react-hooks": reactHooks },
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "max-len": ["error", { code: 300, ignorePattern: '^\\s*"[A-Za-z0-9+/=]{100,}",?$' }],     // the test JPEGs
    },
  },
);
