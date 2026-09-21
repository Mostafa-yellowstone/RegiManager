import { fetchOwnerInsuranceSummary, fetchOwnerSpaces } from '@/lib/api';
import { activeDateParams } from '@/lib/dateRange';
import type { DateRangePreset, InsuranceSummaryPayload } from '@/types/models';

function money(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export async function orgHasInsuranceAccess(): Promise<boolean> {
  try {
    const data = await fetchOwnerSpaces();
    const spaces = (data?.spaces || data?.results || []) as Array<{ key?: string }>;
    return spaces.some((s) => (s.key || '').toLowerCase() === 'insurance');
  } catch {
    return false;
  }
}

export async function getInsuranceSummary(_preset: DateRangePreset): Promise<InsuranceSummaryPayload> {
  const { from_date, to_date } = activeDateParams();
  const raw = await fetchOwnerInsuranceSummary({ from_date, to_date });

  const totalsRaw = raw?.totals || {};
  const companies = Array.isArray(raw?.companies) ? raw.companies : [];

  return {
    available: Boolean(raw?.available),
    as_of: String(raw?.as_of || ''),
    range: {
      from: raw?.range?.from ?? from_date,
      to: raw?.range?.to ?? to_date,
    },
    totals: {
      earned_commission: money(totalsRaw.earned_commission),
      received_commission: money(totalsRaw.received_commission),
      unearned_commission: money(totalsRaw.unearned_commission),
      period_premium: money(totalsRaw.period_premium),
      period_commission: money(totalsRaw.period_commission),
      period_broker_fee: money(totalsRaw.period_broker_fee),
      book_premium: money(totalsRaw.book_premium),
      period_bound_count: Number(totalsRaw.period_bound_count) || 0,
      active_policy_count: Number(totalsRaw.active_policy_count) || 0,
    },
    companies: companies.map((row: any) => ({
      id: Number(row.id),
      name: String(row.name || 'Carrier'),
      active_count: Number(row.active_count) || 0,
      earned_commission: money(row.earned_commission),
      received_commission: money(row.received_commission),
      unearned_commission: money(row.unearned_commission),
      period_premium: money(row.period_premium),
      period_commission: money(row.period_commission),
      period_broker_fee: money(row.period_broker_fee),
      period_bound_count: Number(row.period_bound_count) || 0,
      book_premium: money(row.book_premium),
    })),
  };
}
