import type { Space } from '@/types/models';

import { MOCK_SPACES } from '@/data/mock/spaces';

function delay(ms = 420) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function listSpaces(): Promise<Space[]> {
  await delay(180);
  return MOCK_SPACES;
}

export async function getSpace(id: string): Promise<Space | undefined> {
  await delay(120);
  return MOCK_SPACES.find((s) => s.id === id);
}
