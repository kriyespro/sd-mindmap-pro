/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.jinja',
    './mindmap-todo/templates/**/*.html',
    './users/forms.py',
    './planner/forms.py',
    './teams/forms.py',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        ink: {
          DEFAULT: '#0f172a',
          muted: '#475569',
          faint: '#94a3b8',
        },
        brand: {
          DEFAULT: '#4f46e5',
          light: '#6366f1',
          dark: '#3730a3',
        },
      },
      transitionDuration: {
        180: '180ms',
      },
    },
  },
  plugins: [],
};
