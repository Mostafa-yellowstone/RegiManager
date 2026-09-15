import type {
  DateRangePreset,
  FinancialOverview,
  PulseDashboardPayload,
  ServiceBreakdownRow,
  SpaceIdOrAll,
  TargetProgressRow,
} from '@/types/models';

import { MOCK_SERVICES, MOCK_SPACES } from './spaces';

function mulberry32(seed: number) {
  return function next() {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedFrom(spaceId: SpaceIdOrAll, range: DateRangePreset) {
  const s = `${spaceId}:${range}`;
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) + 1;
}

function rangeScale(range: DateRangePreset): number {
  switch (range) {
    case 'today':
    case 'yesterday':
      return 1;
    case 'week':
      return 6.2;
    case 'month':
      return 24;
    case 'ytd':
      return 180;
    case 'custom':
      return 10;
  }
}

function spaceFactor(spaceId: SpaceIdOrAll): number {
  if (spaceId === 'all') return 1;
  if (spaceId === 'space-midtown') return 0.42;
  if (spaceId === 'space-brooklyn') return 0.33;
  return 0.25;
}

function buildSeries(rng: () => number, points: number, base: number) {
  const now = Date.now();
  const step = 24 * 60 * 60 * 1000;
  const out: Array<{ timestamp: number; value: number }> = [];
  let cursor = base * 0.7;
  for (let i = points - 1; i >= 0; i--) {
    cursor = Math.max(80, cursor + (rng() - 0.45) * base * 0.18);
    out.push({ timestamp: now - i * step, value: Math.round(cursor) });
  }
  return out;
}

function buildOverview(spaceId: SpaceIdOrAll, range: DateRangePreset): FinancialOverview {
  const rng = mulberry32(seedFrom(spaceId, range));
  const scale = rangeScale(range) * spaceFactor(spaceId) * (spaceId === 'all' ? 1 : 1 / 0.42);
  const gross = Math.round((4200 + rng() * 1800) * scale);
  const expenses = Math.round(gross * (0.48 + rng() * 0.12));
  const profit = gross - expenses;
  const margin = (profit / gross) * 100;

  const revDelta = (rng() - 0.35) * 28;
  const expDelta = (rng() - 0.5) * 18;
  const profitDelta = (rng() - 0.3) * 32;
  const marginDelta = (rng() - 0.4) * 8;

  const points = range === 'today' || range === 'yesterday' ? 12 : range === 'week' ? 7 : 14;

  return {
    space_id: spaceId,
    range,
    gross_revenue: gross,
    total_expenses: expenses,
    net_profit: profit,
    profit_margin_pct: Number(margin.toFixed(1)),
    badges: {
      revenue: { label: 'vs prior', delta_pct: Number(revDelta.toFixed(1)) },
      expenses: { label: 'vs prior', delta_pct: Number(expDelta.toFixed(1)) },
      profit: { label: 'vs prior', delta_pct: Number(profitDelta.toFixed(1)) },
      margin: { label: 'vs prior', delta_pct: Number(marginDelta.toFixed(1)) },
    },
    series: buildSeries(rng, points, gross / points),
  };
}

function buildServices(spaceId: SpaceIdOrAll, range: DateRangePreset): ServiceBreakdownRow[] {
  const rng = mulberry32(seedFrom(spaceId, range) + 99);
  const scale = rangeScale(range);
  const services =
    spaceId === 'all' ? MOCK_SERVICES : MOCK_SERVICES.filter((s) => s.space_id === spaceId);

  return services
    .map((svc) => {
      const bookings = Math.max(2, Math.round((8 + rng() * 22) * (scale / 6)));
      const revenue = Math.round(bookings * svc.price * (0.85 + rng() * 0.2));
      const hour = 10 + Math.floor(rng() * 8);
      return {
        service_id: svc.id,
        name: svc.name,
        category: svc.category,
        bookings,
        revenue,
        avg_ticket: Math.round(revenue / bookings),
        peak_hour_label: `${hour}:00–${hour + 1}:00`,
      };
    })
    .sort((a, b) => b.revenue - a.revenue);
}

function buildTargets(spaceId: SpaceIdOrAll, range: DateRangePreset): TargetProgressRow[] {
  const rng = mulberry32(seedFrom(spaceId, range) + 7);
  const factor = spaceFactor(spaceId) * (spaceId === 'all' ? 1 : 1 / 0.42);

  const dailyTarget = Math.round(3200 * factor);
  const weeklyTarget = Math.round(18500 * factor);
  const monthlyTarget = Math.round(78000 * factor);

  const dailyActual = Math.round(dailyTarget * (0.55 + rng() * 0.5));
  const weeklyActual = Math.round(weeklyTarget * (0.5 + rng() * 0.45));
  const monthlyActual = Math.round(monthlyTarget * (0.35 + rng() * 0.4));

  const dayOfMonth = new Date().getDate();
  const daysInMonth = 30;
  const monthlyRunRate = Math.round((monthlyActual / Math.max(1, dayOfMonth)) * daysInMonth);

  return [
    {
      period: 'daily',
      type: 'revenue',
      target_amount: dailyTarget,
      actual_amount: dailyActual,
      progress_pct: Math.min(100, Math.round((dailyActual / dailyTarget) * 100)),
      run_rate_amount: dailyActual,
      run_rate_label: 'Today pace',
    },
    {
      period: 'weekly',
      type: 'revenue',
      target_amount: weeklyTarget,
      actual_amount: weeklyActual,
      progress_pct: Math.min(100, Math.round((weeklyActual / weeklyTarget) * 100)),
      run_rate_amount: Math.round(weeklyActual * (7 / Math.max(1, new Date().getDay() || 7))),
      run_rate_label: 'Week run rate',
    },
    {
      period: 'monthly',
      type: 'revenue',
      target_amount: monthlyTarget,
      actual_amount: monthlyActual,
      progress_pct: Math.min(100, Math.round((monthlyActual / monthlyTarget) * 100)),
      run_rate_amount: monthlyRunRate,
      run_rate_label: 'Projected EOM',
    },
  ];
}

export function buildPulseDashboard(
  spaceId: SpaceIdOrAll,
  range: DateRangePreset,
): PulseDashboardPayload {
  const overview = buildOverview(spaceId, range);
  const scale = rangeScale(range);

  return {
    overview,
    services: buildServices(spaceId, range),
    targets: buildTargets(spaceId, range),
    space_summaries: MOCK_SPACES.map((space, idx) => {
      const share = [0.42, 0.33, 0.25][idx] ?? 0.3;
      return {
        space_id: space.id,
        name: space.name,
        location: space.location,
        revenue: Math.round(overview.gross_revenue * (spaceId === 'all' ? share : spaceId === space.id ? 1 : 0.15)),
      };
    }).map((row) => ({
      ...row,
      revenue: Math.max(row.revenue, Math.round(400 * scale * 0.2)),
    })),
  };
}
