import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { getLeaderboard } from '@/data/repositories/leaderboardRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import type { LeaderboardRow } from '@/types/models';

type TeamMode = 'today' | 'leaderboard';

export default function TeamScreen() {
  const [mode, setMode] = useState<TeamMode>('today');
  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <View style={{ flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingTop: 12 }}>
        {(
          [
            { id: 'today', label: 'Today' },
            { id: 'leaderboard', label: 'Leaderboard' },
          ] as const
        ).map((opt) => {
          const active = mode === opt.id;
          return (
            <Pressable
              key={opt.id}
              onPress={() => {
                void hapticSelection();
                setMode(opt.id);
              }}
              style={{
                flex: 1,
                alignItems: 'center',
                borderRadius: 12,
                paddingVertical: 10,
                backgroundColor: active ? Colors.teal : Colors.white,
                borderWidth: 1,
                borderColor: active ? Colors.teal : Colors.border,
              }}
            >
              <Text style={{ fontFamily: Fonts.bold, fontSize: 14, color: active ? Colors.cream : Colors.navy }}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      {mode === 'today' ? <TodayTeam /> : <Leaderboard />}
    </View>
  );
}

type SortKey = 'total_earned' | 'policies_bound' | 'broker_fee' | 'dmv_jobs';

const SORTS: Array<{ id: SortKey; label: string }> = [
  { id: 'total_earned', label: 'Earned' },
  { id: 'policies_bound', label: 'Binds' },
  { id: 'broker_fee', label: 'Broker fees' },
  { id: 'dmv_jobs', label: 'DMV jobs' },
];

function Leaderboard() {
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const [sortKey, setSortKey] = useState<SortKey>('total_earned');

  const query = useQuery({
    queryKey: ['pulse-leaderboard', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => getLeaderboard(),
    enabled: Boolean(selectedOrg?.id),
  });

  const rows = useMemo(() => {
    const list = [...(query.data?.agents ?? [])];
    list.sort((a, b) => b[sortKey] - a[sortKey] || b.total_earned - a.total_earned);
    return list;
  }, [query.data?.agents, sortKey]);
  const leaderValue = rows.length ? rows[0][sortKey] : 0;
  const totals = query.data?.totals;

  return (
    <ScrollView
      contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 120, gap: 12 }}
      refreshControl={
        <RefreshControl
          refreshing={query.isFetching && !query.isLoading}
          onRefresh={() => {
            void hapticLight();
            void query.refetch();
          }}
          tintColor={Colors.teal}
        />
      }
    >
      <ConnectedDateRangeSelector />

      {totals ? (
        <View
          style={{
            borderRadius: 16,
            backgroundColor: Colors.white,
            borderWidth: 1,
            borderColor: Colors.border,
            padding: 16,
          }}
        >
          <Text style={{ fontFamily: Fonts.bold, fontSize: 11, letterSpacing: 0.6, color: Colors.tealDeep }}>
            TEAM EARNED FOR THE OFFICE
          </Text>
          <Text style={{ marginTop: 6, fontFamily: Fonts.extrabold, fontSize: 28, color: Colors.navy }}>
            {formatMoney(totals.total_earned)}
          </Text>
          <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted, lineHeight: 18 }}>
            Commission {formatMoney(totals.commission, true)} · Broker fees {formatMoney(totals.broker_fee, true)} ·
            DMV office fees {formatMoney(totals.dmv_office_keeps, true)}
          </Text>
          <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {totals.policies_bound} binds · {totals.dmv_jobs} DMV jobs
          </Text>
        </View>
      ) : null}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {SORTS.map((opt) => {
          const active = sortKey === opt.id;
          return (
            <Pressable
              key={opt.id}
              onPress={() => {
                void hapticSelection();
                setSortKey(opt.id);
              }}
              style={{
                borderRadius: 999,
                paddingHorizontal: 14,
                paddingVertical: 8,
                backgroundColor: active ? Colors.tealSoft : Colors.white,
                borderWidth: 1,
                borderColor: active ? Colors.teal : Colors.border,
              }}
            >
              <Text style={{ fontFamily: Fonts.bold, fontSize: 13, color: active ? Colors.tealDeep : Colors.muted }}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {query.isError ? (
        <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
          {(query.error as Error)?.message || 'Could not load the leaderboard'}
        </Text>
      ) : null}

      {query.isLoading ? (
        <>
          <SkeletonBlock height={96} />
          <SkeletonBlock height={96} />
          <SkeletonBlock height={96} />
        </>
      ) : rows.length === 0 ? (
        <Text style={{ textAlign: 'center', marginTop: 24, fontFamily: Fonts.medium, color: Colors.muted }}>
          No team activity in this range.
        </Text>
      ) : (
        rows.map((row, index) => (
          <LeaderRow
            key={row.membership_id ?? `other-${index}`}
            row={row}
            position={index + 1}
            sortKey={sortKey}
            share={leaderValue > 0 ? row[sortKey] / leaderValue : 0}
          />
        ))
      )}
    </ScrollView>
  );
}

function sortValueLabel(row: LeaderboardRow, sortKey: SortKey): string {
  if (sortKey === 'policies_bound') return `${row.policies_bound} binds`;
  if (sortKey === 'dmv_jobs') return `${row.dmv_jobs} jobs`;
  return formatMoney(row[sortKey]);
}

function LeaderRow({
  row,
  position,
  sortKey,
  share,
}: {
  row: LeaderboardRow;
  position: number;
  sortKey: SortKey;
  share: number;
}) {
  const podium = position <= 3 && row[sortKey] > 0;
  return (
    <View
      style={{
        backgroundColor: Colors.white,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: position === 1 && podium ? Colors.teal : Colors.border,
        padding: 14,
        gap: 10,
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <View
          style={{
            width: 34,
            height: 34,
            borderRadius: 17,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: podium ? (position === 1 ? Colors.orangeSoft : Colors.tealSoft) : Colors.navySoft,
          }}
        >
          <Text
            style={{
              fontFamily: Fonts.extrabold,
              fontSize: 14,
              color: podium ? (position === 1 ? Colors.orangeDeep : Colors.tealDeep) : Colors.muted,
            }}
          >
            {position}
          </Text>
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>
            {row.name}
          </Text>
          {row.role ? (
            <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
              {row.role.charAt(0).toUpperCase() + row.role.slice(1)}
            </Text>
          ) : null}
        </View>
        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 16, color: Colors.teal }}>
          {sortValueLabel(row, sortKey)}
        </Text>
      </View>
      <View style={{ height: 6, borderRadius: 3, backgroundColor: Colors.navySoft, overflow: 'hidden' }}>
        <View
          style={{
            width: `${Math.max(0, Math.min(1, share)) * 100}%`,
            height: '100%',
            borderRadius: 3,
            backgroundColor: Colors.teal,
          }}
        />
      </View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        <Chip label={`${row.policies_bound} binds`} bg={Colors.tealSoft} fg={Colors.tealDeep} />
        <Chip label={`Commission ${formatMoney(row.commission, true)}`} bg={Colors.greenSoft} fg={Colors.greenDeep} />
        <Chip label={`Broker ${formatMoney(row.broker_fee, true)}`} bg={Colors.purpleSoft} fg={Colors.purple} />
        <Chip
          label={`${row.dmv_jobs} DMV · office ${formatMoney(row.dmv_office_keeps, true)}`}
          bg={Colors.orangeSoft}
          fg={Colors.orangeDeep}
        />
      </View>
    </View>
  );
}

function Chip({ label, bg, fg }: { label: string; bg: string; fg: string }) {
  return (
    <View style={{ borderRadius: 999, paddingHorizontal: 9, paddingVertical: 4, backgroundColor: bg }}>
      <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: fg }}>{label}</Text>
    </View>
  );
}

function TodayTeam() {
  const router = useRouter();
  const { selectedOrg } = useAuth();
  const agentsQuery = useQuery({
    queryKey: ['pulse-agents', selectedOrg?.id],
    queryFn: () => listOwnerAgents(),
    enabled: Boolean(selectedOrg?.id),
  });

  const agents = useMemo(() => {
    const rows = [...(agentsQuery.data?.agents ?? [])];
    rows.sort((a, b) => {
      if (a.is_late !== b.is_late) return Number(b.is_late) - Number(a.is_late);
      if (a.attendance_open !== b.attendance_open) return Number(b.attendance_open) - Number(a.attendance_open);
      return a.name.localeCompare(b.name);
    });
    return rows;
  }, [agentsQuery.data?.agents]);

  const here = agents.filter((agent) => agent.attendance_open).length;
  const late = agents.filter((agent) => agent.is_late).length;
  const stillOut = agents.filter((agent) => !agent.attendance_open && !agent.is_late && !agent.is_on_time).length;

  return (
    <View style={{ flex: 1 }}>
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 120, gap: 10 }}
        refreshControl={
          <RefreshControl
            refreshing={agentsQuery.isFetching && !agentsQuery.isLoading}
            onRefresh={() => {
              void hapticLight();
              void agentsQuery.refetch();
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Stat label="Here" value={here} />
          <Stat label="Late" value={late} alert={late > 0} />
          <Stat label="Still out" value={stillOut} />
        </View>
        {agentsQuery.data?.work_date ? (
          <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            Today · {agentsQuery.data.work_date}
          </Text>
        ) : null}
        {agentsQuery.isError ? (
          <Text style={{ fontFamily: Fonts.semibold, color: Colors.danger }}>
            {(agentsQuery.error as Error)?.message || 'Could not load the team'}
          </Text>
        ) : null}
        {agentsQuery.isLoading ? (
          <>
            <SkeletonBlock height={76} />
            <SkeletonBlock height={76} />
          </>
        ) : agents.length === 0 ? (
          <Text style={{ textAlign: 'center', marginTop: 24, fontFamily: Fonts.medium, color: Colors.muted }}>
            No one on the roster.
          </Text>
        ) : (
          agents.map((agent) => (
            <Pressable
              key={agent.membership_id}
              onPress={() => {
                void hapticSelection();
                router.push({
                  pathname: '/person/[id]' as any,
                  params: {
                    id: String(agent.membership_id),
                    name: agent.name,
                    role: agent.role,
                    late: agent.is_late ? '1' : '0',
                    here: agent.attendance_open ? '1' : '0',
                    label: agent.attendance_label,
                    jobs: String(agent.service_records_total),
                  },
                });
              }}
              style={{
                backgroundColor: Colors.white,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: Colors.border,
                padding: 14,
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 12,
              }}
            >
              <View style={{ flex: 1 }}>
                <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>{agent.name}</Text>
                <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
                  {agent.attendance_label}
                </Text>
                <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                  {agent.service_records_total} jobs
                </Text>
              </View>
              <StatusMark late={agent.is_late} here={agent.attendance_open} />
            </Pressable>
          ))
        )}
      </ScrollView>
    </View>
  );
}

function Stat({ label, value, alert }: { label: string; value: number; alert?: boolean }) {
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: alert ? Colors.orangeSoft : Colors.white,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: Colors.border,
        padding: 12,
      }}
    >
      <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>{label}</Text>
      <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 22, color: Colors.navy }}>{value}</Text>
    </View>
  );
}

function StatusMark({ late, here }: { late: boolean; here: boolean }) {
  const label = late ? 'Late' : here ? 'Here' : 'Out';
  const bg = late ? Colors.orangeSoft : here ? Colors.greenSoft : Colors.navySoft;
  const fg = late ? Colors.orangeDeep : here ? Colors.greenDeep : Colors.muted;
  return (
    <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: bg }}>
      <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: fg }}>{label}</Text>
    </View>
  );
}
