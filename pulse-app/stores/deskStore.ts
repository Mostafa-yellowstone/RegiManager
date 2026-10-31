import { create } from 'zustand';

export type WorkKind = 'all' | 'desk' | 'insurance' | 'motorclub' | 'tlc';
export type WorkStatus = 'all' | 'waiting' | 'done' | 'failed' | 'refund';

type DeskState = {
  query: string;
  kind: WorkKind;
  status: WorkStatus;
  person: string;
  setQuery: (query: string) => void;
  setKind: (kind: WorkKind) => void;
  setStatus: (status: WorkStatus) => void;
  setPerson: (person: string) => void;
};

export const useDeskStore = create<DeskState>((set) => ({
  query: '',
  kind: 'all',
  status: 'all',
  person: '',
  setQuery: (query) => set({ query }),
  setKind: (kind) => set({ kind }),
  setStatus: (status) => set({ status }),
  setPerson: (person) => set({ person }),
}));
