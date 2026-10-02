/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Every colour resolves to a CSS variable holding space separated RGB
      // channels, so light and dark share one definition and Tailwind opacity
      // modifiers (bg-primary/5) keep working in both themes.
      colors: {
        primary: {
          DEFAULT: 'rgb(var(--primary) / <alpha-value>)',
          dark: 'rgb(var(--primary-600) / <alpha-value>)',
          light: 'rgb(var(--primary-bg) / <alpha-value>)',
          50: 'rgb(var(--primary-bg) / <alpha-value>)',
          100: 'rgb(var(--primary-line) / <alpha-value>)',
          500: 'rgb(var(--primary) / <alpha-value>)',
          600: 'rgb(var(--primary-600) / <alpha-value>)',
          700: 'rgb(var(--primary-700) / <alpha-value>)',
        },
        area: {
          cls: 'rgb(var(--area-cls) / <alpha-value>)',
          att: 'rgb(var(--area-att) / <alpha-value>)',
          prj: 'rgb(var(--area-prj) / <alpha-value>)',
          ann: 'rgb(var(--area-ann) / <alpha-value>)',
        },
        'area-cls-bg': 'rgb(var(--area-cls-bg) / <alpha-value>)',
        'area-att-bg': 'rgb(var(--area-att-bg) / <alpha-value>)',
        'area-prj-bg': 'rgb(var(--area-prj-bg) / <alpha-value>)',
        'area-ann-bg': 'rgb(var(--area-ann-bg) / <alpha-value>)',
        navy: 'rgb(var(--nav) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        'page-bg': 'rgb(var(--canvas) / <alpha-value>)',
        'border-default': 'rgb(var(--line) / <alpha-value>)',
        'text-primary': 'rgb(var(--ink) / <alpha-value>)',
        'text-secondary': 'rgb(var(--ink-2) / <alpha-value>)',
        'text-muted': 'rgb(var(--ink-3) / <alpha-value>)',
        success: 'rgb(var(--ok) / <alpha-value>)',
        warning: 'rgb(var(--wn) / <alpha-value>)',
        danger: 'rgb(var(--bd) / <alpha-value>)',
        info: 'rgb(var(--primary) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        'xs': '4px',
        'sm': '6px',
        'md': '8px',
        'DEFAULT': '10px',
        'lg': '12px',
        'xl': '14px',
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        'flat': 'var(--sh-1)',
        'card': 'var(--sh-2)',
        'raised': 'var(--sh-3)',
        'card-hover': 'var(--sh-3)',
        'dropdown': 'var(--sh-3)',
        'modal': 'var(--sh-pop)',
      },
    },
  },
  plugins: [],
};
