/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,ts}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#080B12',
        'surf-1': '#161B27',
        'surf-2': '#1C2234',
        'surf-3': '#222A40',
        primary: '#5B8AF0',
        'primary-dim': 'rgba(91,138,240,0.12)',
        'primary-med': 'rgba(91,138,240,0.20)',
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        'on-surf': '#E2E8F0',
        'on-var': '#8892A8',
        border: 'rgba(255,255,255,0.07)',
        'border-med': 'rgba(255,255,255,0.13)',
      },
      fontFamily: {
        sans: ['-apple-system', 'Segoe UI', 'Roboto', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
