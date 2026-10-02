module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '.eslintrc.cjs'],
  parserOptions: {
    ecmaVersion: 'latest',
    ecmaFeatures: { jsx: true },
    sourceType: 'module',
  },
  settings: { react: { version: '18.0' } },
  plugins: ['react-refresh'],
  rules: {
    // The new JSX transform makes these unnecessary, and prop-types are not
    // used anywhere in this codebase.
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    // Several files deliberately export helpers next to their component
    // (projectUi.jsx, the API modules), which this rule would flag.
    'react-refresh/only-export-components': 'off',
    'no-unused-vars': ['error', { args: 'none', varsIgnorePattern: '^[A-Z_]' }],
  },
};
