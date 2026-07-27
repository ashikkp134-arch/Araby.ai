/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#07111f',
          900: '#0b1628',
          800: '#12233d',
          700: '#1a3358',
        },
        accent: {
          DEFAULT: '#2dd4bf',
          soft: '#99f6e4',
          deep: '#0f766e',
        },
        sand: {
          50: '#f7f4ef',
          100: '#efe8dc',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"IBM Plex Sans"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      boxShadow: {
        panel: '0 20px 60px rgba(7, 17, 31, 0.35)',
      },
      keyframes: {
        rise: {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(45, 212, 191, 0.35)' },
          '50%': { boxShadow: '0 0 0 10px rgba(45, 212, 191, 0)' },
        },
        drift: {
          '0%': { transform: 'translate3d(0,0,0)' },
          '50%': { transform: 'translate3d(12px,-8px,0)' },
          '100%': { transform: 'translate3d(0,0,0)' },
        },
      },
      animation: {
        rise: 'rise 0.6s ease-out both',
        pulseGlow: 'pulseGlow 2.4s ease-in-out infinite',
        drift: 'drift 12s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
