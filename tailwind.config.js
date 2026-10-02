/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#3F35B5',
          dark: '#30278F',
          light: '#EEF0FF',
          50: '#EEF0FF',
          100: '#D5D9FE',
          200: '#B0B8FD',
          300: '#8B91FC',
          400: '#6769FA',
          500: '#3F35B5',
          600: '#30278F',
          700: '#241D6A',
          800: '#1A1545',
          900: '#080D16',
        },
        navy: '#080D16',
        surface: '#FFFFFF',
        'page-bg': '#F6F7FB',
        'border-default': '#E5E7EB',
        'text-primary': '#111827',
        'text-secondary': '#6B7280',
        success: '#16A34A',
        warning: '#F59E0B',
        danger: '#DC2626',
        info: '#2563EB',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        'sm': '6px',
        'md': '8px',
        'DEFAULT': '10px',
        'lg': '12px',
        'xl': '14px',
        '2xl': '16px',
        '3xl': '24px',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(15, 23, 42, 0.04)',
        'card-hover': '0 4px 20px rgba(15, 23, 42, 0.08)',
        'dropdown': '0 10px 40px rgba(15, 23, 42, 0.12)',
        'modal': '0 20px 60px rgba(15, 23, 42, 0.15)',
      },
    },
  },
  plugins: [],
};
