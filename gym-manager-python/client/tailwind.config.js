/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: { 950: '#071425', 900: '#0B1F3A', 800: '#102A43', 700: '#163A5F' },
      },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
      boxShadow: { popover: '0 10px 28px rgba(15, 23, 42, 0.12)' },
    },
  },
  plugins: [],
}
