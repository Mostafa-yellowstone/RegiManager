import { create } from 'zustand';

import type { DateRangePreset } from '@/types/models';

type DateRangeState = {
  preset: DateRangePreset;
  customStart: string | null;
  customEnd: string | null;
  setPreset: (preset: DateRangePreset) => void;
  setCustomRange: (start: string, end: string) => void;
};

export const useDateRangeStore = create<DateRangeState>((set) => ({
  preset: 'week',
  customStart: null,
  customEnd: null,
  setPreset: (preset) => set({ preset, customStart: null, customEnd: null }),
  setCustomRange: (start, end) =>
    set({ preset: 'custom', customStart: start, customEnd: end }),
}));
