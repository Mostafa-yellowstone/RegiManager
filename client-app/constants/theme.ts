export const Colors = {
  // Brand Primary (navy wallet design)
  primary: '#1A2B48',
  primaryMid: '#1E3A5F',
  primaryLight: '#2B4A6F',
  primarySubtle: '#EEF2F7',

  // Gold accent (brand seal / highlights)
  gold: '#C9A227',
  goldSoft: '#F7F0D8',

  // Chat CTA (mockup orange)
  chatOrange: '#E85D04',
  chatOrangeSoft: '#FFF4ED',

  // Policy card gradient anchors
  policyTeal: '#0D9488',
  policyTealDeep: '#0F766E',
  policyTealSoft: '#CCFBF1',

  // Accent & Status
  teal: '#0D9488',
  tealSoft: '#F0FDFA',
  success: '#059669',
  successLight: '#ECFDF5',
  warning: '#D97706',
  warningLight: '#FFFBEB',
  danger: '#DC2626',
  dangerLight: '#FEF2F2',
  info: '#2563EB',

  // Backgrounds & Surfaces
  navy: '#1A2B48',
  navyMid: '#243B55',
  cream: '#F5F7FA',
  white: '#FFFFFF',
  surfaceElevated: '#FFFFFF',
  card: '#FFFFFF',

  // Typography
  text: '#0F172A',
  textSecondary: '#475569',
  muted: '#64748B',
  mutedLight: '#94A3B8',

  // Borders & Dividers
  border: '#E2E8F0',
  borderDark: '#CBD5E1',
  borderSubtle: '#F1F5F9',
  shadow: '#0F172A',
};

export const Typography = {
  hero: { fontSize: 28, fontWeight: '800' as const, letterSpacing: -0.5 },
  h1: { fontSize: 24, fontWeight: '800' as const, letterSpacing: -0.4 },
  h2: { fontSize: 18, fontWeight: '700' as const, letterSpacing: -0.2 },
  h3: { fontSize: 16, fontWeight: '700' as const },
  body: { fontSize: 14, fontWeight: '400' as const, lineHeight: 20 },
  bodyBold: { fontSize: 14, fontWeight: '600' as const, lineHeight: 20 },
  caption: { fontSize: 12, fontWeight: '500' as const, lineHeight: 16 },
  badge: { fontSize: 11, fontWeight: '700' as const, letterSpacing: 0.5 },
};

export const Radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  pill: 9999,
};

export const Shadows = {
  card: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 12,
    elevation: 3,
  },
  popover: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 6,
  },
};
