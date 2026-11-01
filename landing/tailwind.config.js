/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'primary-black': '#050505',
        'hero-dark': '#090909',
        'card-surface': '#151515',
        'elevated-surface': '#222224',
        graphite: '#38383C',
        silver: '#D8D8DC',
        'soft-white': '#F4F4F5',
        'secondary-text': '#A2A2A8',
        'fine-border': '#4D4D51',
        'zien-gold': '#E5C07B',
      },
      fontFamily: {
        sans: ['Inter', 'Geist', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      backgroundImage: {
        'radial-top': 'radial-gradient(1000px 500px at 50% 0%, rgba(216, 216, 220, 0.12) 0%, rgba(9, 9, 9, 0.9) 65%, #050505 100%)',
        'gold-glow': 'radial-gradient(circle at center, rgba(229, 192, 123, 0.15) 0%, transparent 70%)',
      },
      animation: {
        'pulse-subtle': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
