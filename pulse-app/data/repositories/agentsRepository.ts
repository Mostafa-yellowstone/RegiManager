import { fetchOwnerAgents } from '@/lib/api';
import { adaptAgents } from '@/data/adapters/pulseAdapter';
import type { AgentRosterRow } from '@/types/models';

export async function listOwnerAgents(): Promise<{
  work_date: string;
  agents: AgentRosterRow[];
}> {
  const payload = await fetchOwnerAgents();
  return {
    work_date: payload?.work_date || '',
    agents: adaptAgents(payload),
  };
}
