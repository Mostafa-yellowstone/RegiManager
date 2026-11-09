import { useWindowDimensions } from 'react-native';

/** Type and spacing that follow the phone width, rotation, and the system font size. */
export function usePulseScale() {
  const { width, height, fontScale } = useWindowDimensions();
  const shortest = Math.min(width, height);
  const widthFactor = shortest < 340 ? 0.86 : shortest < 390 ? 0.94 : shortest > 720 ? 1.12 : 1;
  const scale = Math.min(Math.max(fontScale, 0.85), 1.4) * widthFactor;
  const fs = (size: number) => Math.round(size * scale);

  return {
    fs,
    width,
    height,
    isLandscape: width > height,
    pad: width > height ? 22 : 16,
    gap: width > height ? 12 : 14,
  };
}
