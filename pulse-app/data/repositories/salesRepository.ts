import { fetchOwnerFinanceRecords } from '@/lib/api';
import { activeDateParams } from '@/lib/dateRange';
import { adaptFinanceRecords } from '@/data/adapters/pulseAdapter';
import type { ActivityRow, DateRangePreset } from '@/types/models';

export async function listSalesActivity(_preset: DateRangePreset): Promise<ActivityRow[]> {
  const { from_date, to_date } = activeDateParams();
  const [dmv, insurance] = await Promise.all([
    fetchOwnerFinanceRecords({ category: 'dmv', from_date, to_date, limit: 30 }),
    fetchOwnerFinanceRecords({ category: 'insurance', from_date, to_date, limit: 20 }).catch(
      () => ({ results: [] }),
    ),
  ]);
  return [
    ...adaptFinanceRecords(dmv, 'DMV'),
    ...adaptFinanceRecords(insurance, 'Insurance'),
  ].sort((a, b) => (a.date < b.date ? 1 : -1));
}
