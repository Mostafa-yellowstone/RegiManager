/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#1A2B48',
          mid: '#243B55',
          soft: '#EEF2F7',
        },
        gold: {
          DEFAULT: '#C9A227',
          soft: '#F7F0D8',
        },
        cream: '#F5F7FA',
        ink: '#0F172A',
        muted: '#64748B',
        border: '#E2E8F0',
        success: '#059669',
        danger: '#DC2626',
        warning: '#D97706',
      },
      spacing: {
        // Reinforce 8pt grid (Tailwind already uses 4/8)
      },
      fontSize: {
        display: ['32px', { lineHeight: '40px', fontWeight: '800', letterSpacing: '-0.5px' }],
        title: ['20px', { lineHeight: '28px', fontWeight: '700' }],
        body: ['15px', { lineHeight: '22px', fontWeight: '400' }],
        caption: ['12px', { lineHeight: '16px', fontWeight: '500' }],
      },
    },
  },
  plugins: [],
};
