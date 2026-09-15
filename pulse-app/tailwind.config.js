/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#0F3D4C',
          mid: '#164E63',
          soft: '#E6F4F1',
        },
        teal: {
          DEFAULT: '#0D9488',
          deep: '#0F766E',
          soft: '#CCFBF1',
        },
        gold: {
          DEFAULT: '#C9A227',
          soft: '#F7F0D8',
        },
        cream: '#F7FAFC',
        ink: '#0F172A',
        muted: '#64748B',
        border: '#E2E8F0',
        success: '#27AE60',
        danger: '#DC2626',
        warning: '#F2994A',
        orange: '#F2994A',
        purple: '#9B51E0',
        pulseBlue: '#2D9CDB',
      },
      fontSize: {
        display: ['34px', { lineHeight: '40px', fontWeight: '800', letterSpacing: '-0.6px' }],
        title: ['20px', { lineHeight: '28px', fontWeight: '700' }],
        body: ['15px', { lineHeight: '22px', fontWeight: '400' }],
        caption: ['12px', { lineHeight: '16px', fontWeight: '600' }],
      },
      boxShadow: {
        card: '0 8px 24px rgba(15, 61, 76, 0.08)',
      },
    },
  },
  plugins: [],
};
