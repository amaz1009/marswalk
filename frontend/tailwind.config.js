/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        mars: {
          bg: '#0c0d10',
          panel: '#15171e',
          border: '#282c37',
          orange: '#d9532f',
          red: '#c0392b',
          muted: '#8b92a5',
        },
      },
    },
  },
  plugins: [],
};
