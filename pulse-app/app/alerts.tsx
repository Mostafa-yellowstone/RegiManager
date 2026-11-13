import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { fetchOwnerNotifications, markAllOwnerNotificationsRead, markOwnerNotificationRead } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';

type Filter = 'all' | 'insurance' | 'dmv' | 'expense';
type Kind = 'insurance' | 'dmv' | 'expense' | 'other';

type AlertLine = { label: string; amount: string; group?: 'dmv' | 'office'; total?: boolean };

type AlertRow = {
  id: number;
  event_type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  client_name?: string | null;
  data?: {
    kind?: 'insurance' | 'dmv' | 'expense';
    client?: string;
    subtitle?: string;
    by?: string;
    note?: string;
    headline?: { label: string; amount: string };
    lines?: AlertLine[];
  };
};

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'insurance', label: 'Insurance' },
  { id: 'dmv', label: 'DMV' },
  { id: 'expense', label: 'Expenses' },
];

function kindOf(row: AlertRow): Kind {
  if (row.data?.kind) return row.data.kind;
  if (row.event_type.startsWith('policy_')) return 'insurance';
  if (row.event_type === 'dmv_transaction' || row.event_type === 'pulse_daily_snapshot') return 'dmv';
  if (row.event_type === 'expense_alert') return 'expense';
  return 'other';
}

const TONES: Record<Kind, { fg: string; bg: string }> = {
  insurance: { fg: Colors.teal, bg: Colors.tealSoft },
  dmv: { fg: Colors.blue, bg: Colors.blueSoft },
  expense: { fg: Colors.orangeDeep, bg: Colors.orangeSoft },
  other: { fg: Colors.purple, bg: Colors.purpleSoft },
};

function relativeTime(iso: string): string {
  const when = new Date(iso).getTime();
  if (!Number.isFinite(when)) return '';
  const minutes = Math.round((Date.now() - when) / 60000);
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function dayLabel(iso: string): string {
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return 'Earlier';
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const diffDays = Math.floor((start.getTime() - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  if (diffDays <= 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function toMoney(value: string | undefined) {
  const n = Number(value);
  return formatMoney(Number.isFinite(n) ? n : 0);
}

export default function AlertsScreen() {
  const { selectedOrg } = useAuth();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>('all');

  const alerts = useQuery({
    queryKey: ['pulse-alerts', selectedOrg?.id],
    queryFn: () => fetchOwnerNotifications(),
    enabled: Boolean(selectedOrg?.id),
    refetchInterval: 60_000,
  });

  const markRead = useMutation({
    mutationFn: (id: number) => markOwnerNotificationRead(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['pulse-alerts'] }),
  });
  const markAll = useMutation({
    mutationFn: () => markAllOwnerNotificationsRead(),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['pulse-alerts'] }),
  });

  const allRows: AlertRow[] = alerts.data?.notifications || [];
  const unreadBy = useMemo(() => {
    const counts = { all: 0, insurance: 0, dmv: 0, expense: 0 };
    for (const row of allRows) {
      if (row.is_read) continue;
      counts.all += 1;
      const kind = kindOf(row);
      if (kind !== 'other') counts[kind] += 1;
    }
    return counts;
  }, [allRows]);

  const groups = useMemo(() => {
    const rows = filter === 'all' ? allRows : allRows.filter((row) => kindOf(row) === filter);
    const out: Array<{ label: string; rows: AlertRow[] }> = [];
    for (const row of rows) {
      const label = dayLabel(row.created_at);
      const last = out[out.length - 1];
      if (last && last.label === label) last.rows.push(row);
      else out.push({ label, rows: [row] });
    }
    return out;
  }, [allRows, filter]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: Colors.cream }}
      contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }}
      refreshControl={
        <RefreshControl
          refreshing={alerts.isFetching && !alerts.isLoading}
          onRefresh={() => {
            void hapticLight();
            void alerts.refetch();
          }}
          tintColor={Colors.teal}
        />
      }
    >
      {unreadBy.all > 0 ? (
        <Pressable
          onPress={() => {
            void hapticSelection();
            markAll.mutate();
          }}
          hitSlop={8}
          style={{ alignSelf: 'flex-end' }}
        >
          <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.teal }}>Mark all read</Text>
        </Pressable>
      ) : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {FILTERS.map((opt) => {
          const active = filter === opt.id;
          const count = unreadBy[opt.id];
          return (
            <Pressable
              key={opt.id}
              onPress={() => {
                void hapticSelection();
                setFilter(opt.id);
              }}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                borderRadius: 999,
                paddingHorizontal: 12,
                paddingVertical: 8,
                backgroundColor: active ? Colors.teal : Colors.white,
                borderWidth: 1,
                borderColor: active ? Colors.teal : Colors.border,
              }}
            >
              <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: active ? Colors.white : Colors.navy }}>
                {opt.label}
              </Text>
              {count > 0 ? (
                <View
                  style={{
                    minWidth: 18,
                    borderRadius: 9,
                    paddingHorizontal: 5,
                    paddingVertical: 1,
                    alignItems: 'center',
                    backgroundColor: active ? Colors.white : Colors.danger,
                  }}
                >
                  <Text style={{ fontFamily: Fonts.extrabold, fontSize: 10, color: active ? Colors.teal : '#fff' }}>
                    {count}
                  </Text>
                </View>
              ) : null}
            </Pressable>
          );
        })}
      </ScrollView>

      {alerts.isError ? (
        <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
          {(alerts.error as Error)?.message || 'Could not load alerts'}
        </Text>
      ) : null}

      {alerts.isLoading ? (
        <>
          <SkeletonBlock height={120} />
          <SkeletonBlock height={120} />
        </>
      ) : groups.length === 0 ? (
        <View style={{ marginTop: 40, alignItems: 'center', gap: 6 }}>
          <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>You're all caught up</Text>
          <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted, textAlign: 'center' }}>
            Bound policies, DMV transactions and expense alerts show up here and on your phone.
          </Text>
        </View>
      ) : (
        groups.map((group) => (
          <View key={group.label} style={{ gap: 8 }}>
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 11,
                letterSpacing: 0.6,
                textTransform: 'uppercase',
                color: Colors.muted,
              }}
            >
              {group.label}
            </Text>
            {group.rows.map((row) => (
              <AlertCard
                key={row.id}
                row={row}
                onPress={() => {
                  void hapticSelection();
                  if (!row.is_read) markRead.mutate(Number(row.id));
                }}
              />
            ))}
          </View>
        ))
      )}
    </ScrollView>
  );
}

function AlertCard({ row, onPress }: { row: AlertRow; onPress: () => void }) {
  const kind = kindOf(row);
  const tone = TONES[kind];
  const data = row.data || {};
  const lines = data.lines || [];
  const dmvLines = lines.filter((line) => line.group === 'dmv');
  const officeLines = lines.filter((line) => line.group === 'office');
  const plainLines = lines.filter((line) => !line.group);

  return (
    <Pressable
      onPress={onPress}
      style={{
        backgroundColor: Colors.white,
        borderRadius: 18,
        borderWidth: 1,
        borderColor: row.is_read ? Colors.border : tone.fg,
        padding: 14,
        gap: 10,
      }}
    >
      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start' }}>
        <View
          style={{
            width: 40,
            height: 40,
            borderRadius: 12,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: tone.bg,
          }}
        >
          <KindIcon kind={kind} color={tone.fg} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Text style={{ flex: 1, fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }} numberOfLines={1}>
              {row.title || 'Alert'}
            </Text>
            {!row.is_read ? <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: tone.fg }} /> : null}
            <Text style={{ fontFamily: Fonts.medium, fontSize: 11, color: Colors.muted }}>
              {relativeTime(row.created_at)}
            </Text>
          </View>
          <Text style={{ marginTop: 2, fontFamily: Fonts.bold, fontSize: 13, color: Colors.navyMid }} numberOfLines={1}>
            {data.client || row.client_name || ''}
          </Text>
          {data.subtitle || data.by ? (
            <Text style={{ marginTop: 1, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }} numberOfLines={1}>
              {[data.subtitle, data.by ? `by ${data.by}` : ''].filter(Boolean).join(' · ')}
            </Text>
          ) : null}
        </View>
      </View>

      {data.headline ? (
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            borderRadius: 12,
            paddingHorizontal: 12,
            paddingVertical: 10,
            backgroundColor: tone.bg,
          }}
        >
          <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: tone.fg }}>{data.headline.label}</Text>
          <Text style={{ fontFamily: Fonts.extrabold, fontSize: 20, color: tone.fg }}>
            {toMoney(data.headline.amount)}
          </Text>
        </View>
      ) : null}

      {plainLines.length ? <LineList lines={plainLines} /> : null}
      {officeLines.length ? <LineList title="Office" lines={officeLines} /> : null}
      {dmvLines.length ? <LineList title="Goes to the DMV" lines={dmvLines} /> : null}
      {data.note ? (
        <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }} numberOfLines={2}>
          {data.note}
        </Text>
      ) : null}

      {!data.headline && row.message ? (
        <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted, lineHeight: 18 }}>
          {row.message}
        </Text>
      ) : null}
    </Pressable>
  );
}

function LineList({ title, lines }: { title?: string; lines: AlertLine[] }) {
  return (
    <View style={{ gap: 5 }}>
      {title ? (
        <Text
          style={{
            fontFamily: Fonts.bold,
            fontSize: 10,
            letterSpacing: 0.6,
            textTransform: 'uppercase',
            color: Colors.mutedLight,
          }}
        >
          {title}
        </Text>
      ) : null}
      {lines.map((line) => (
        <View
          key={`${title || ''}-${line.label}`}
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            paddingTop: line.total ? 5 : 0,
            borderTopWidth: line.total ? 1 : 0,
            borderTopColor: Colors.border,
          }}
        >
          <Text style={{ fontFamily: line.total ? Fonts.bold : Fonts.medium, fontSize: 13, color: Colors.navyMid }}>
            {line.label}
          </Text>
          <Text style={{ fontFamily: line.total ? Fonts.extrabold : Fonts.bold, fontSize: 13, color: Colors.navy }}>
            {toMoney(line.amount)}
          </Text>
        </View>
      ))}
    </View>
  );
}

function KindIcon({ kind, color }: { kind: Kind; color: string }) {
  const stroke = { fill: 'none', stroke: color, strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
  if (kind === 'expense') {
    return (
      <Svg width={20} height={20} viewBox="0 0 24 24">
        <Path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z" {...stroke} />
        <Path d="M9 8h6M9 12h6M9 16h3" {...stroke} />
      </Svg>
    );
  }
  if (kind === 'insurance') {
    return (
      <Svg width={20} height={20} viewBox="0 0 24 24">
        <Path d="M12 3 4.5 6.2V12c0 4.6 3.1 7.9 7.5 9 4.4-1.1 7.5-4.4 7.5-9V6.2L12 3z" {...stroke} />
        <Path d="M9 12.2 11 14.2l4-4.2" {...stroke} />
      </Svg>
    );
  }
  if (kind === 'dmv') {
    return (
      <Svg width={20} height={20} viewBox="0 0 24 24">
        <Path d="M5 16V11l2-5h10l2 5v5M3.5 16h17" {...stroke} />
        <Circle cx="7.5" cy="16.5" r="1.8" {...stroke} />
        <Circle cx="16.5" cy="16.5" r="1.8" {...stroke} />
        <Path d="M7 11h10" {...stroke} />
      </Svg>
    );
  }
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24">
      <Path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16zM10 20a2 2 0 0 0 4 0" {...stroke} />
    </Svg>
  );
}
