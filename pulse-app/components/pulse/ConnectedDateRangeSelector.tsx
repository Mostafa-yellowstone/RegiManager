import { useDateRangeStore } from '@/stores/dateRangeStore';
import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';

/** Shared date chips wired to the global Pulse date store (includes Custom). */
export function ConnectedDateRangeSelector() {
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const setPreset = useDateRangeStore((s) => s.setPreset);
  const setCustomRange = useDateRangeStore((s) => s.setCustomRange);

  return (
    <DateRangeSelector
      value={preset}
      customStart={customStart}
      customEnd={customEnd}
      onChange={setPreset}
      onCustomRange={setCustomRange}
    />
  );
}
