import { create } from 'zustand';

import type { SpaceIdOrAll } from '@/types/models';

type SpaceState = {
  selectedSpaceId: SpaceIdOrAll;
  setSelectedSpaceId: (id: SpaceIdOrAll) => void;
};

export const useSpaceStore = create<SpaceState>((set) => ({
  selectedSpaceId: 'all',
  setSelectedSpaceId: (id) => set({ selectedSpaceId: id }),
}));
