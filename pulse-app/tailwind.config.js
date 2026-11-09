/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: '#F4F7FB',
          mid: '#A7B0C0',
          soft: '#1C232E',
        },
        teal: {
          DEFAULT: '#3DDC97',
          deep: '#1FA971',
          soft: '#12352A',
        },
        gold: {
          DEFAULT: '#E2B340',
          soft: '#3A3014',
        },
        cream: '#07090C',
        ink: '#F4F7FB',
        muted: '#8E98A8',
        border: '#2A3342',
        success: '#3DDC97',
        danger: '#FF6B6B',
        warning: '#F5A524',
        orange: '#F5A524',
        purple: '#7AA2FF',
        pulseBlue: '#4C8DFF',
        white: '#141922',
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
