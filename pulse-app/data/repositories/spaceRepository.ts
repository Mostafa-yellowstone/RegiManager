import { fetchOwnerSpaces } from '@/lib/api';
import { activeDateParams } from '@/lib/dateRange';
import { adaptSpacesList } from '@/data/adapters/pulseAdapter';
import type { DateRangePreset, SpaceSummary } from '@/types/models';

export async function listSpaces(_preset: DateRangePreset = 'month'): Promise<SpaceSummary[]> {
  const { from_date, to_date } = activeDateParams();
  const payload = await fetchOwnerSpaces({ from_date, to_date });
  return adaptSpacesList(payload, true);
}
