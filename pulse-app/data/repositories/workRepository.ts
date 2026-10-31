import { adaptFinanceRecords } from '@/data/adapters/pulseAdapter';
import {
  fetchOwnerFinanceRecords,
  fetchOwnerMotorclubMemberships,
  fetchOwnerProcesses,
  fetchOwnerTlcPolicies,
} from '@/lib/api';
import { activeDateParams } from '@/lib/dateRange';

export type WorkKind = 'desk' | 'insurance' | 'motorclub' | 'tlc';

export type DeskJob = {
  id: string;
  title: string;
  customer: string;
  person: string;
  status: string;
  kind: WorkKind;
  kindLabel: string;
  amount: number;
  date: string;
  detail: string;
};

export function jobStatusLabel(status: string): string {
  const key = (status || '').toLowerCase();
  if (key === 'pending' || key === 'quoting' || key === 'processing') return 'Waiting';
  if (key === 'completed' || key === 'active' || key === 'approved') return 'Done';
  if (key === 'failed' || key === 'rejected') return 'Needs you';
  if (key === 'refund' || key === 'refunded') return 'Refunded';
  if (key === 'cancelled' || key === 'canceled' || key === 'expired' || key === 'suspended') {
    return 'Closed';
  }
  return status ? status.replace(/_/g, ' ') : '';
}

function money(value: unknown): number {
  const n = Number(String(value ?? '').replace(/,/g, ''));
  return Number.isFinite(n) ? n : 0;
}

function jobsFromProcesses(payload: any): DeskJob[] {
  const rows = payload?.recent_services || [];
  return rows.map((row: any) => ({
    id: `job-${row.id}`,
    title: row.service_type || 'Desk job',
    customer: row.client_name || '',
    person: row.handled_by || '',
    status: row.status || '',
    kind: 'desk' as const,
    kindLabel: 'Desk',
    amount: money(row.processing_fee),
    date: row.transaction_date || '',
    detail: row.case_id ? String(row.case_id) : '',
  }));
}

function jobsFromPayments(
  rows: Array<{ id: string; title: string; subtitle: string; amount: number; date: string }>,
  kind: WorkKind,
  kindLabel: string,
): DeskJob[] {
  return rows.map((row) => ({
    id: `pay-${kind}-${row.id}`,
    title: row.title || 'Payment',
    customer: row.subtitle || '',
    person: '',
    status: '',
    kind,
    kindLabel,
    amount: row.amount,
    date: row.date || '',
    detail: row.subtitle || '',
  }));
}

function jobsFromMotorclub(payload: any): DeskJob[] {
  const rows = payload?.memberships || payload?.results || [];
  return rows.map((row: any) => ({
    id: `mc-${row.id}`,
    title: row.membership_number || 'Motor Club',
    customer: row.client_name || row.b2b_partner_name || '',
    person: row.added_by || '',
    status: row.status || '',
    kind: 'motorclub' as const,
    kindLabel: 'Motor Club',
    amount: money(row.psb_profit),
    date: row.joined_date || row.start_date || '',
    detail: row.plan_type || row.channel_label || '',
  }));
}

function jobsFromTlc(payload: any): DeskJob[] {
  const rows = payload?.policies || payload?.results || [];
  return rows.map((row: any) => ({
    id: `tlc-${row.id}`,
    title: row.policy_number || 'TLC',
    customer: row.named_insured || '',
    person: row.added_by || row.broker_name || '',
    status: row.status || '',
    kind: 'tlc' as const,
    kindLabel: 'TLC',
    amount: 0,
    date: row.effective_date || '',
    detail: [row.carrier, row.plate_number].filter(Boolean).join(' · '),
  }));
}

export async function listDeskJobs(): Promise<DeskJob[]> {
  const { from_date, to_date } = activeDateParams();
  const [processes, dmv, insurance, motorclub, tlc] = await Promise.all([
    fetchOwnerProcesses().catch(() => null),
    fetchOwnerFinanceRecords({ category: 'dmv', from_date, to_date, limit: 40 }).catch(() => ({
      results: [],
    })),
    fetchOwnerFinanceRecords({ category: 'insurance', from_date, to_date, limit: 30 }).catch(() => ({
      results: [],
    })),
    fetchOwnerMotorclubMemberships().catch(() => null),
    fetchOwnerTlcPolicies().catch(() => null),
  ]);

  const jobs = [
    ...jobsFromProcesses(processes),
    ...jobsFromPayments(adaptFinanceRecords(dmv, 'DMV'), 'desk', 'Desk'),
    ...jobsFromPayments(adaptFinanceRecords(insurance, 'Insurance'), 'insurance', 'Insurance'),
    ...jobsFromMotorclub(motorclub),
    ...jobsFromTlc(tlc),
  ];

  jobs.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  return jobs;
}
