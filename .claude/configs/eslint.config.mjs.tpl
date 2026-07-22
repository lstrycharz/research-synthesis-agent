// Starter flat ESLint config — the deterministic floor for JS/TS style + a set
// of correctness rules that map directly to real bugs (the claude-setup
// post-mortem: missing keys, shadowing, unused error bindings all shipped).
//
// Dropped by init-claude (as eslint.config.mjs) for JS/TS projects. Extend per
// project. Protected from agent edits by config-protection — fix code, not config.
//
// Requires: npm i -D eslint @eslint/js typescript-eslint eslint-plugin-react-hooks

import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    plugins: { 'react-hooks': reactHooks },
    rules: {
      // Correctness rules that catch the classes of bug found in review:
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      'no-shadow': 'error',                  // local `set` shadowing Set / an import
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'no-console': 'off',
    },
  },
  { ignores: ['dist/', 'build/', 'coverage/', 'node_modules/'] },
)
