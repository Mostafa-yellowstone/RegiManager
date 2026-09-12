export const Colors = {
  // Brand Primary
  primary: '#1E40AF',
  primaryMid: '#2563EB',
  primaryLight: '#3B82F6',
  primarySubtle: '#EFF6FF',

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
  navy: '#0B192C',
  navyMid: '#1E293B',
  cream: '#F8FAFC',
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
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 2,
  },
  popover: {
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.1,
    shadowRadius: 20,
    elevation: 6,
  },
};

