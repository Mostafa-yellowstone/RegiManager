import type { DateRangePreset } from '@/types/models';
import { useDateRangeStore } from '@/stores/dateRangeStore';

/** Local calendar YYYY-MM-DD (avoid UTC shift from toISOString). */
export function isoLocal(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function parseIsoLocal(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function isValidIso(iso: string | null | undefined): iso is string {
  return Boolean(iso && /^\d{4}-\d{2}-\d{2}$/.test(iso));
}

/** Map Pulse presets to owner API from_date/to_date (YYYY-MM-DD). Always sends both. */
export function presetToDateParams(
  preset: DateRangePreset,
  customStart?: string | null,
  customEnd?: string | null,
): {
  from_date: string;
  to_date: string;
  bucket: 'today' | 'yesterday' | 'week' | 'month' | 'ytd' | 'custom';
} {
  const today = new Date();
  const end = isoLocal(today);

  if (preset === 'custom' && isValidIso(customStart) && isValidIso(customEnd)) {
    const from = customStart <= customEnd ? customStart : customEnd;
    const to = customStart <= customEnd ? customEnd : customStart;
    return { from_date: from, to_date: to, bucket: 'custom' };
  }

  if (preset === 'today') {
    return { from_date: end, to_date: end, bucket: 'today' };
  }

  if (preset === 'yesterday') {
    const y = new Date(today);
    y.setDate(y.getDate() - 1);
    const day = isoLocal(y);
    return { from_date: day, to_date: day, bucket: 'yesterday' };
  }

  if (preset === 'week') {
    const start = new Date(today);
    const day = start.getDay();
    const diff = day === 0 ? 6 : day - 1; // Monday start (matches CRM bank week)
    start.setDate(start.getDate() - diff);
    return { from_date: isoLocal(start), to_date: end, bucket: 'week' };
  }

  if (preset === 'month') {
    const start = new Date(today.getFullYear(), today.getMonth(), 1);
    return { from_date: isoLocal(start), to_date: end, bucket: 'month' };
  }

  if (preset === 'ytd') {
    const start = new Date(today.getFullYear(), 0, 1);
    return { from_date: isoLocal(start), to_date: end, bucket: 'ytd' };
  }

  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  return { from_date: isoLocal(start), to_date: end, bucket: 'custom' };
}

/** Resolve the active Pulse date range from the global store. */
export function activeDateParams() {
  const { preset, customStart, customEnd } = useDateRangeStore.getState();
  return presetToDateParams(preset, customStart, customEnd);
}

export function previousMonthKey(now = new Date()) {
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export function currentMonthKey(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

/** Prior period matching the active Pulse preset (for compare badges). */
export function previousPeriodDateParams(
  preset: DateRangePreset,
  customStart?: string | null,
  customEnd?: string | null,
): {
  from_date: string;
  to_date: string;
} {
  const today = new Date();

  if (preset === 'custom' && isValidIso(customStart) && isValidIso(customEnd)) {
    const from = customStart <= customEnd ? customStart : customEnd;
    const to = customStart <= customEnd ? customEnd : customStart;
    const start = parseIsoLocal(from);
    const end = parseIsoLocal(to);
    const days = Math.max(0, Math.round((end.getTime() - start.getTime()) / 86400000));
    const priorEnd = new Date(start);
    priorEnd.setDate(priorEnd.getDate() - 1);
    const priorStart = new Date(priorEnd);
    priorStart.setDate(priorStart.getDate() - days);
    return { from_date: isoLocal(priorStart), to_date: isoLocal(priorEnd) };
  }

  if (preset === 'today' || preset === 'yesterday') {
    const d = new Date(today);
    d.setDate(d.getDate() - (preset === 'today' ? 1 : 2));
    const day = isoLocal(d);
    return { from_date: day, to_date: day };
  }

  if (preset === 'week') {
    const start = new Date(today);
    const day = start.getDay();
    const diff = day === 0 ? 6 : day - 1;
    start.setDate(start.getDate() - diff - 7);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return { from_date: isoLocal(start), to_date: isoLocal(end) };
  }

  if (preset === 'ytd') {
    const start = new Date(today.getFullYear() - 1, 0, 1);
    const end = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
    return { from_date: isoLocal(start), to_date: isoLocal(end) };
  }

  // month / custom fallback → previous calendar month
  const start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  const end = new Date(today.getFullYear(), today.getMonth(), 0);
  return { from_date: isoLocal(start), to_date: isoLocal(end) };
}

export function compareBadgeLabel(preset: DateRangePreset): string {
  if (preset === 'today') return 'vs yesterday';
  if (preset === 'yesterday') return 'vs prior day';
  if (preset === 'week') return 'vs prior week';
  if (preset === 'ytd') return 'vs prior YTD';
  if (preset === 'custom') return 'vs prior range';
  return 'vs prior month';
}

export function formatRangeChipLabel(start: string | null, end: string | null): string {
  if (!isValidIso(start) || !isValidIso(end)) return 'Custom';
  if (start === end) return start.slice(5);
  return `${start.slice(5)} to ${end.slice(5)}`;
}
