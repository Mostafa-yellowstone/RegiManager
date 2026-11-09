export const Colors = {
  // Dark desk from the Pulse boards. Green for money in, blue for what's left, amber for money out.
  teal: '#3DDC97',
  tealDeep: '#1FA971',
  tealSoft: '#12352A',
  tealMid: '#67E8B5',

  orange: '#F5A524',
  orangeSoft: '#3A2A12',
  orangeDeep: '#E08A12',

  green: '#3DDC97',
  greenSoft: '#12352A',
  greenDeep: '#1FA971',

  purple: '#7AA2FF',
  purpleSoft: '#152038',
  purpleDeep: '#4C74D4',

  blue: '#4C8DFF',
  blueSoft: '#152033',

  navy: '#F4F7FB',
  navyMid: '#A7B0C0',
  navySoft: '#1C232E',

  cream: '#07090C',
  white: '#141922',
  ink: '#F4F7FB',
  muted: '#8E98A8',
  mutedLight: '#66707F',
  border: '#2A3342',

  success: '#3DDC97',
  danger: '#FF6B6B',
  warning: '#F5A524',
  gold: '#E2B340',
  goldSoft: '#3A3014',
} as const;

export const Fonts = {
  regular: 'Manrope_400Regular',
  medium: 'Manrope_500Medium',
  semibold: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  extrabold: 'Manrope_800ExtraBold',
} as const;

export type MetricAccent = 'teal' | 'orange' | 'green' | 'purple' | 'blue';

export const MetricAccents: Record<
  MetricAccent,
  { main: string; soft: string; deep: string; border: string }
> = {
  teal: { main: Colors.teal, soft: Colors.tealSoft, deep: Colors.tealDeep, border: '#1E4D38' },
  orange: { main: Colors.orange, soft: Colors.orangeSoft, deep: Colors.orangeDeep, border: '#5A3E12' },
  green: { main: Colors.green, soft: Colors.greenSoft, deep: Colors.greenDeep, border: '#1E4D38' },
  purple: { main: Colors.purple, soft: Colors.purpleSoft, deep: Colors.purpleDeep, border: '#24365C' },
  blue: { main: Colors.blue, soft: Colors.blueSoft, deep: Colors.blue, border: '#24365C' },
};
