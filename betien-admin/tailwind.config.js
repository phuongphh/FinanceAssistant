/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        gold: '#B8945A',
        'gold-50': '#F8F1E6',
        ink: {
          50: '#F5F7FA',
          100: '#E8EEF5',
          500: '#52677A',
          700: '#1C3A55',
          900: '#0A2540',
        },
        paper: '#FBF7EF',
        porcelain: '#FFFDF8',
        hairline: '#E8E0D3',
        sage: '#5A7A4F',
        burgundy: '#8B2635',
        orange: '#C97B4A',
        'vn-flag-red': '#DA251D',
      },
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        body: ['Geist', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        hairline: '0 0 0 1px #E8E0D3',
      },
    },
  },
  plugins: [],
};
