import { fetchOwnerSpaces } from '@/lib/api';
import { presetToDateParams } from '@/lib/dateRange';
import { adaptSpacesList } from '@/data/adapters/pulseAdapter';
import type { DateRangePreset, SpaceSummary } from '@/types/models';

export async function listSpaces(preset: DateRangePreset = 'month'): Promise<SpaceSummary[]> {
  const { from_date, to_date } = presetToDateParams(preset);
  const payload = await fetchOwnerSpaces({ from_date, to_date });
  return adaptSpacesList(payload, true);
}
