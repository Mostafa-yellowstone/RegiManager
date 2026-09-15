import { buildPulseDashboard } from '@/data/mock/metrics';
import type { DateRangePreset, PulseDashboardPayload, SpaceIdOrAll } from '@/types/models';

function delay(ms = 520) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function getPulseDashboard(
  spaceId: SpaceIdOrAll,
  range: DateRangePreset,
): Promise<PulseDashboardPayload> {
  await delay();
  return buildPulseDashboard(spaceId, range);
}
