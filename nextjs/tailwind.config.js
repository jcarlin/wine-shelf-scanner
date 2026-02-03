/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Wine app specific colors
        wine: '#722F37',
        star: '#FFCC00',
        'app-bg': '#1a1a2e',
        'badge-bg': 'rgba(0, 0, 0, 0.7)',
        'top-three-border': 'rgba(255, 204, 0, 0.6)',
        'toast-bg': 'rgba(0, 0, 0, 0.8)',
        'debug-bg': 'rgba(0, 0, 0, 0.95)',
      },
      fontSize: {
        rating: '48px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'fade-out': 'fadeOut 0.3s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'scan-line': 'scanLine 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        fadeOut: {
          '0%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
        slideUp: {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        scanLine: {
          '0%, 100%': { top: '0%' },
          '50%': { top: '100%' },
        },
      },
    },
  },
  plugins: [],
};
