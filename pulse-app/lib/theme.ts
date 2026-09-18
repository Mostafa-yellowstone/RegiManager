export const Colors = {
  // Pulse green-first palette
  teal: '#0D9488',
  tealDeep: '#0F766E',
  tealSoft: '#CCFBF1',
  tealMid: '#14B8A6',

  orange: '#EA8A3C',
  orangeSoft: '#FFF4E8',
  orangeDeep: '#C2410C',

  green: '#059669',
  greenSoft: '#ECFDF5',
  greenDeep: '#047857',

  // Kept as soft green variants (not purple/blue rainbow)
  purple: '#0F766E',
  purpleSoft: '#F0FDFA',
  purpleDeep: '#115E59',

  blue: '#0D9488',
  blueSoft: '#E6FFFA',

  navy: '#0B3D3A',
  navyMid: '#115E59',
  navySoft: '#E6F4F1',

  cream: '#F3FAF7',
  white: '#FFFFFF',
  ink: '#0F1F1C',
  muted: '#5B6F6A',
  mutedLight: '#8AA09A',
  border: '#D7E8E2',

  success: '#059669',
  danger: '#DC2626',
  warning: '#EA8A3C',
  gold: '#B8860B',
  goldSoft: '#F7F0D8',
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
  teal: { main: Colors.teal, soft: Colors.tealSoft, deep: Colors.tealDeep, border: '#99F6E4' },
  orange: { main: Colors.orange, soft: Colors.orangeSoft, deep: Colors.orangeDeep, border: '#FED7AA' },
  green: { main: Colors.green, soft: Colors.greenSoft, deep: Colors.greenDeep, border: '#A7F3D0' },
  purple: { main: Colors.purple, soft: Colors.purpleSoft, deep: Colors.purpleDeep, border: '#99F6E4' },
  blue: { main: Colors.blue, soft: Colors.blueSoft, deep: Colors.tealDeep, border: '#99F6E4' },
};
