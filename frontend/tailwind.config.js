/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        rail: {
          navy: '#0f172a',
          blue: '#1e3a8a',
          steel: '#334155',
          accent: '#2563eb',
        },
        priority: {
          critical: '#dc2626',
          high: '#ea580c',
          medium: '#ca8a04',
          low: '#16a34a',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
