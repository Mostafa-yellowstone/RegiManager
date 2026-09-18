/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#0B3D3A',
          mid: '#115E59',
          soft: '#E6F4F1',
        },
        teal: {
          DEFAULT: '#0D9488',
          deep: '#0F766E',
          soft: '#CCFBF1',
        },
        gold: {
          DEFAULT: '#B8860B',
          soft: '#F7F0D8',
        },
        cream: '#F3FAF7',
        ink: '#0F1F1C',
        muted: '#5B6F6A',
        border: '#D7E8E2',
        success: '#059669',
        danger: '#DC2626',
        warning: '#EA8A3C',
        orange: '#EA8A3C',
        purple: '#0F766E',
        pulseBlue: '#0D9488',
      },
      fontFamily: {
        sans: ['Manrope_500Medium'],
        medium: ['Manrope_500Medium'],
        semibold: ['Manrope_600SemiBold'],
        bold: ['Manrope_700Bold'],
        extrabold: ['Manrope_800ExtraBold'],
      },
      fontSize: {
        display: ['34px', { lineHeight: '40px', fontWeight: '800', letterSpacing: '-0.6px' }],
        title: ['20px', { lineHeight: '28px', fontWeight: '700' }],
        body: ['15px', { lineHeight: '22px', fontWeight: '400' }],
        caption: ['12px', { lineHeight: '16px', fontWeight: '600' }],
      },
      boxShadow: {
        card: '0 8px 24px rgba(11, 61, 58, 0.08)',
      },
    },
  },
  plugins: [],
};
