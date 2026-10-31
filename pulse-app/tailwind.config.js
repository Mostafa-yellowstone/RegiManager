/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#241C18',
          mid: '#5C5148',
          soft: '#F3EBE3',
        },
        teal: {
          DEFAULT: '#C4512F',
          deep: '#8E341C',
          soft: '#F8E4DC',
        },
        gold: {
          DEFAULT: '#E3A008',
          soft: '#FFF3D0',
        },
        cream: '#F7F1E8',
        ink: '#241C18',
        muted: '#7A6E64',
        border: '#E7DDD2',
        success: '#C4512F',
        danger: '#B42318',
        warning: '#C4512F',
        orange: '#E07A55',
        purple: '#7A4E8A',
        pulseBlue: '#2E4A7A',
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
