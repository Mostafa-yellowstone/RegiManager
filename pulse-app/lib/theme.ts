export const Colors = {
  // Warm sand, ink, and terracotta. The welcome band carries the brighter colors.
  teal: '#C4512F',
  tealDeep: '#8E341C',
  tealSoft: '#F8E4DC',
  tealMid: '#E07A55',

  orange: '#E07A55',
  orangeSoft: '#FDE8DF',
  orangeDeep: '#8E341C',

  green: '#C4512F',
  greenSoft: '#F8E4DC',
  greenDeep: '#8E341C',

  purple: '#7A4E8A',
  purpleSoft: '#F3E8F6',
  purpleDeep: '#4E2E5C',

  blue: '#2E4A7A',
  blueSoft: '#E4EAF4',

  navy: '#241C18',
  navyMid: '#5C5148',
  navySoft: '#F3EBE3',

  cream: '#F7F1E8',
  white: '#FFFCF8',
  ink: '#241C18',
  muted: '#7A6E64',
  mutedLight: '#B3A69B',
  border: '#E7DDD2',

  success: '#C4512F',
  danger: '#B42318',
  warning: '#C4512F',
  gold: '#E3A008',
  goldSoft: '#FFF3D0',
} as const;

/** Manrope — load via useFonts in root layout before rendering UI. */
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
  teal: { main: Colors.teal, soft: Colors.tealSoft, deep: Colors.tealDeep, border: '#F0D2C6' },
  orange: { main: Colors.orange, soft: Colors.orangeSoft, deep: Colors.orangeDeep, border: '#F0D2C6' },
  green: { main: Colors.green, soft: Colors.greenSoft, deep: Colors.greenDeep, border: '#F0D2C6' },
  purple: { main: Colors.purple, soft: Colors.purpleSoft, deep: Colors.purpleDeep, border: '#E6D4EC' },
  blue: { main: Colors.blue, soft: Colors.blueSoft, deep: Colors.blue, border: '#D5DEEC' },
};
