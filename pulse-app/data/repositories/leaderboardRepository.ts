import { fetchOwnerExpenseWatch, fetchOwnerLeaderboard, saveOwnerExpenseWatch } from '@/lib/api';
import { activeDateParams } from '@/lib/dateRange';
import type { ExpenseWatchPayload, ExpenseWatchSettings, LeaderboardPayload } from '@/types/models';

function money(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export async function getLeaderboard(): Promise<LeaderboardPayload> {
  const { from_date, to_date } = activeDateParams();
  const raw = await fetchOwnerLeaderboard({ from_date, to_date });
  const totals = raw?.totals || {};
  return {
    range: { from: String(raw?.range?.from || from_date), to: String(raw?.range?.to || to_date) },
    agents: (Array.isArray(raw?.agents) ? raw.agents : []).map((row: any) => ({
      rank: Number(row.rank) || 0,
      membership_id: row.membership_id == null ? null : Number(row.membership_id),
      name: String(row.name || 'Agent'),
      role: String(row.role || ''),
      policies_bound: Number(row.policies_bound) || 0,
      premium: money(row.premium),
      commission: money(row.commission),
      broker_fee: money(row.broker_fee),
      dmv_jobs: Number(row.dmv_jobs) || 0,
      dmv_office_keeps: money(row.dmv_office_keeps),
      total_earned: money(row.total_earned),
    })),
    totals: {
      policies_bound: Number(totals.policies_bound) || 0,
      commission: money(totals.commission),
      broker_fee: money(totals.broker_fee),
      dmv_jobs: Number(totals.dmv_jobs) || 0,
      dmv_office_keeps: money(totals.dmv_office_keeps),
      total_earned: money(totals.total_earned),
    },
  };
}

function adaptExpenseWatch(raw: any): ExpenseWatchPayload {
  const settings = raw?.settings || {};
  return {
    settings: {
      enabled: Boolean(settings.enabled),
      single_expense_limit: money(settings.single_expense_limit),
      category_jump_percent: Number(settings.category_jump_percent) || 0,
    },
    month: String(raw?.month || ''),
    categories: (Array.isArray(raw?.categories) ? raw.categories : []).map((row: any) => ({
      segment: row.segment === 'insurance' ? 'insurance' : 'dmv',
      category: String(row.category || 'Expense'),
      this_month: money(row.this_month),
      last_month: money(row.last_month),
      change_pct: row.change_pct == null ? null : money(row.change_pct),
      over: Boolean(row.over),
    })),
  };
}

export async function getExpenseWatch(): Promise<ExpenseWatchPayload> {
  return adaptExpenseWatch(await fetchOwnerExpenseWatch());
}

export async function updateExpenseWatch(settings: ExpenseWatchSettings): Promise<ExpenseWatchPayload> {
  return adaptExpenseWatch(
    await saveOwnerExpenseWatch({
      enabled: settings.enabled,
      single_expense_limit: settings.single_expense_limit.toFixed(2),
      category_jump_percent: Math.round(settings.category_jump_percent),
    }),
  );
}
