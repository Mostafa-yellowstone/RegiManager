export const Colors = {
  // Mockup-aligned Pulse palette
  teal: '#0D9488',
  tealDeep: '#0F766E',
  tealSoft: '#CCFBF1',
  tealMid: '#14B8A6',

  orange: '#F2994A',
  orangeSoft: '#FFF4E8',
  orangeDeep: '#D97706',

  green: '#27AE60',
  greenSoft: '#E8F8EF',
  greenDeep: '#059669',

  purple: '#9B51E0',
  purpleSoft: '#F3E8FF',
  purpleDeep: '#7C3AED',

  blue: '#2D9CDB',
  blueSoft: '#E8F4FC',

  navy: '#0F3D4C',
  navyMid: '#164E63',
  navySoft: '#E6F4F1',

  cream: '#F7FAFC',
  white: '#FFFFFF',
  ink: '#0F172A',
  muted: '#64748B',
  mutedLight: '#94A3B8',
  border: '#E2E8F0',

  success: '#27AE60',
  danger: '#DC2626',
  warning: '#F2994A',
  gold: '#C9A227',
  goldSoft: '#F7F0D8',
} as const;

export type MetricAccent = 'teal' | 'orange' | 'green' | 'purple' | 'blue';

export const MetricAccents: Record<
  MetricAccent,
  { main: string; soft: string; deep: string; border: string }
> = {
  teal: { main: Colors.teal, soft: Colors.tealSoft, deep: Colors.tealDeep, border: '#99F6E4' },
  orange: { main: Colors.orange, soft: Colors.orangeSoft, deep: Colors.orangeDeep, border: '#FED7AA' },
  green: { main: Colors.green, soft: Colors.greenSoft, deep: Colors.greenDeep, border: '#A7F3D0' },
  purple: { main: Colors.purple, soft: Colors.purpleSoft, deep: Colors.purpleDeep, border: '#E9D5FF' },
  blue: { main: Colors.blue, soft: Colors.blueSoft, deep: '#1D4ED8', border: '#BFDBFE' },
};
