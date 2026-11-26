// Lint the hook rules (F-046) and accessibility basics (jsx-a11y, Q1.3): rules-of-hooks and exhaustive-deps catch the main bug class here (a
// stale value after a refetch). Every switch-off must say why ("-- reason"), and a switch-off that
// no longer hides anything fails the run. Lines stay under 300 characters (F-034).
// Layout is Prettier's job (npm run format, .prettierrc.json, checked in CI).
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "test-results/**", "playwright-report/**"] },
  {
    files: ["src/**/*.{ts,tsx}", "e2e/**/*.ts", "e2e-local/**/*.ts"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    linterOptions: { reportUnusedDisableDirectives: "error" },
    rules: {
      ...jsxA11y.flatConfigs.recommended.rules,
      "jsx-a11y/aria-role": ["error", { ignoreNonDOM: true }], // FormRenderer's role="expert" is a prop
      "jsx-a11y/label-has-associated-control": ["error", { depth: 3 }], // the label text sits in <strong> inside a <span>
      "jsx-a11y/no-autofocus": "off", // only a dialog's first box, the sign-in box and a just-opened search take focus
      "jsx-a11y/media-has-caption": "off", // the videos are inspection recordings with no speech to caption
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "max-len": ["error", { code: 300, ignorePattern: '^\\s*"[A-Za-z0-9+/=]{100,}",?$' }], // the test JPEGs
    },
  },
);
