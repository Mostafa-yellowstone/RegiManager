import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { RevenueChart } from '@/components/pulse/RevenueChart';
import { ConnectedDateRangeSelector } from '@/components/pulse/ConnectedDateRangeSelector';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { fetchOwnerNotifications } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { formatMoney, formatPct } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { buildAttentionItems } from '@/lib/ownerInsights';
import { usePulseScale } from '@/lib/responsive';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import { useDeskStore } from '@/stores/deskStore';
import type { ComparativeBadge } from '@/types/models';

export default function PulseScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { selectedOrg, organizations, selectOrganization, user } = useAuth();
  const { fs, pad, width } = usePulseScale();
  const preset = useDateRangeStore((s) => s.preset);
  const customStart = useDateRangeStore((s) => s.customStart);
  const customEnd = useDateRangeStore((s) => s.customEnd);
  const setKind = useDeskStore((s) => s.setKind);
  const setStatus = useDeskStore((s) => s.setStatus);

  const dash = useQuery({
    queryKey: ['pulse-home', selectedOrg?.id, preset, customStart, customEnd],
    queryFn: () => getPulseDashboard('all', preset),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 0,
  });

  const agentsQuery = useQuery({
    queryKey: ['pulse-agents', selectedOrg?.id],
    queryFn: () => listOwnerAgents(),
    enabled: Boolean(selectedOrg?.id),
    staleTime: 0,
  });

  const alertsQuery = useQuery({
    queryKey: ['pulse-alerts', selectedOrg?.id],
    queryFn: () => fetchOwnerNotifications(),
    enabled: Boolean(selectedOrg?.id),
  });

  const refetchDesk = dash.refetch;
  const refetchAgents = agentsQuery.refetch;
  useFocusEffect(
    useCallback(() => {
      void refetchDesk();
      void refetchAgents();
    }, [refetchDesk, refetchAgents]),
  );

  const overview = dash.data?.overview;
  const agents = agentsQuery.data?.agents ?? [];
  const late = agents.filter((agent) => agent.is_late).length;
  const here = agents.filter((agent) => agent.attendance_open).length;
  const onTime = agents.filter((agent) => agent.is_on_time).length;
  const attention = buildAttentionItems({
    overview,
    agents,
    spaceSummaries: dash.data?.space_summaries,
  }).slice(0, 1);
  const bestSpace = [...(dash.data?.space_summaries ?? [])].sort((a, b) => b.profit - a.profit)[0];
  const unread = Number(alertsQuery.data?.unread_count || 0);
  const firstName = (user?.full_name || user?.username || '').trim().split(/\s+/)[0] || '';
  const initial = (firstName || 'P').slice(0, 1).toUpperCase();
  const cardBasis = width > 720 ? '23%' : '47%';

  async function onPickOrg() {
    if (organizations.length < 2) return;
    await hapticSelection();
    Alert.alert(
      'Switch office',
      undefined,
      organizations.map((org) => ({
        text: org.city ? `${org.name} · ${org.city}` : org.name,
        onPress: () => {
          void selectOrganization(org.id);
        },
      })),
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        contentContainerStyle={{ padding: pad, paddingBottom: 120, gap: 14 }}
        refreshControl={
          <RefreshControl
            refreshing={(dash.isFetching || agentsQuery.isFetching) && !dash.isLoading}
            onRefresh={() => {
              void hapticLight();
              void dash.refetch();
              void agentsQuery.refetch();
              void queryClient.invalidateQueries({ queryKey: ['pulse-alerts'] });
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ fontFamily: Fonts.bold, fontSize: fs(12), letterSpacing: 1.4, color: Colors.teal }}>
              REGIMANAGER
            </Text>
            <Text style={{ fontFamily: Fonts.extrabold, fontSize: fs(34), color: Colors.navy, letterSpacing: -0.8 }}>
              Pulse
            </Text>
            <Text style={{ fontFamily: Fonts.medium, fontSize: fs(14), color: Colors.muted }}>
              {firstName ? `${firstName}, here is the office.` : 'Here is the office.'}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Pressable
              accessibilityLabel="Alerts"
              onPress={() => {
                void hapticLight();
                router.push('/alerts' as any);
              }}
              style={iconButton}
            >
              <Text style={{ fontFamily: Fonts.bold, color: Colors.navy }}>!</Text>
              {unread > 0 ? (
                <View style={badge}>
                  <Text style={{ color: '#07090C', fontFamily: Fonts.bold, fontSize: 9 }}>
                    {unread > 9 ? '9+' : unread}
                  </Text>
                </View>
              ) : null}
            </Pressable>
            <Pressable
              accessibilityLabel="Settings"
              onPress={() => {
                void hapticLight();
                router.push('/settings');
              }}
              style={[iconButton, { borderRadius: 20 }]}
            >
              <Text style={{ fontFamily: Fonts.extrabold, color: Colors.navy }}>{initial}</Text>
            </Pressable>
          </View>
        </View>

        <Pressable onPress={() => void onPickOrg()} style={officeRow}>
          <Text numberOfLines={1} style={{ flex: 1, fontFamily: Fonts.bold, fontSize: fs(14), color: Colors.navy }}>
            {selectedOrg?.name || 'No office'}
          </Text>
          {selectedOrg?.city ? (
            <Text style={{ fontFamily: Fonts.medium, fontSize: fs(13), color: Colors.muted }}>{selectedOrg.city}</Text>
          ) : null}
          {organizations.length > 1 ? (
            <Text style={{ fontFamily: Fonts.bold, color: Colors.teal }}>▾</Text>
          ) : null}
        </Pressable>

        <ConnectedDateRangeSelector />

        {!selectedOrg?.id ? (
          <EmptyCard title="No office" body="Sign in with an owner account to open this desk." />
        ) : dash.isError ? (
          <EmptyCard
            title="Could not load the desk"
            body={(dash.error as Error)?.message || 'Check the connection and try again.'}
            action="Retry"
            onAction={() => void dash.refetch()}
          />
        ) : dash.isLoading || !overview ? (
          <View style={{ gap: 12 }}>
            <SkeletonBlock height={88} />
            <SkeletonBlock height={160} />
            <SkeletonBlock height={180} />
          </View>
        ) : (
          <>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              <MetricTile
                basis={cardBasis}
                label="DMV Profit"
                hint="Processing fee"
                value={formatMoney(overview.dmv_net_profit)}
                badge={overview.badges.dmv}
                onPress={() => {
                  void hapticSelection();
                  router.navigate('/(tabs)/expenses');
                }}
              />
              <MetricTile
                basis={cardBasis}
                label="Insurance pay"
                hint="Commission + broker fee"
                value={formatMoney(overview.insurance_profit)}
                badge={overview.badges.insurance}
                onPress={() => {
                  void hapticSelection();
                  router.navigate('/(tabs)/insurance');
                }}
              />
              <MetricTile
                basis={cardBasis}
                label="Money in"
                hint="Bank deposits"
                value={overview.cashflow_available ? formatMoney(overview.bank_income) : '—'}
                onPress={() => {
                  void hapticSelection();
                  router.navigate('/(tabs)/expenses');
                }}
              />
              <MetricTile
                basis={cardBasis}
                label="Money out"
                hint="Bank expenses"
                value={overview.cashflow_available ? formatMoney(overview.bank_expenses) : '—'}
                badge={overview.cashflow_available ? overview.badges.expenses : undefined}
                onPress={() => {
                  void hapticSelection();
                  router.navigate('/(tabs)/expenses');
                }}
              />
            </View>

            <Pressable
              onPress={() => {
                void hapticSelection();
                router.navigate('/(tabs)/expenses');
              }}
              style={card}
            >
              <Text style={quiet}>What's left</Text>
              <Text
                adjustsFontSizeToFit
                numberOfLines={1}
                style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: fs(28), color: Colors.navy }}
              >
                {overview.cashflow_available ? formatMoney(overview.net_cash_flow) : '—'}
              </Text>
              <Text style={[quiet, { marginTop: 4 }]}>
                Money in minus money out
                {typeof overview.left_delta_pct === 'number'
                  ? ` · ${formatPct(overview.left_delta_pct, 0)} versus the previous period`
                  : ''}
              </Text>
            </Pressable>

            <RevenueChart data={overview.series} />

            <Pressable
              onPress={() => {
                void hapticSelection();
                if (attention[0]) router.navigate(attention[0].href);
              }}
              style={[card, { backgroundColor: attention[0] ? Colors.goldSoft : Colors.white }]}
            >
              <Text style={{ fontFamily: Fonts.bold, fontSize: fs(15), color: Colors.gold }}>
                {attention[0] ? 'Needs attention' : 'All clear'}
              </Text>
              <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: fs(14), color: Colors.navy }}>
                {attention[0] ? `${attention[0].title}. ${attention[0].body}` : 'Nothing on the desk needs you right now.'}
              </Text>
            </Pressable>

            <View style={card}>
              <Text style={section}>The desk</Text>
              <Text style={[quiet, { marginTop: 2 }]}>Staff counts are today. Jobs follow the dates above.</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
                <Stat label="On duty" value={String(here)} onPress={() => router.navigate('/(tabs)/staff')} />
                <Stat label="On time" value={String(onTime)} onPress={() => router.navigate('/(tabs)/staff')} />
                <Stat label="Late" value={String(late)} alert={late > 0} onPress={() => router.navigate('/(tabs)/staff')} />
                <Stat
                  label="DMV jobs"
                  value={String(overview.records_count || 0)}
                  onPress={() => {
                    setKind('desk');
                    setStatus('all');
                    router.navigate('/(tabs)/sales');
                  }}
                />
                <Stat
                  label="Binds"
                  value={String(overview.insurance_bound_count || 0)}
                  onPress={() => router.navigate('/(tabs)/insurance')}
                />
              </View>
            </View>

            <View style={card}>
              <Text style={section}>Worth knowing</Text>
              {overview.badges.profit ? (
                <Text style={{ marginTop: 8, fontFamily: Fonts.medium, fontSize: fs(14), color: Colors.navy }}>
                  Desk profit {formatPct(overview.badges.profit.delta_pct, 0)} {overview.badges.profit.label}.
                </Text>
              ) : (
                <Text style={[quiet, { marginTop: 8 }]}>Desk profit is DMV Profit plus insurance pay.</Text>
              )}
              {bestSpace ? (
                <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: fs(14), color: Colors.navy }}>
                  Strongest space: {bestSpace.name} · {formatMoney(bestSpace.profit)}
                </Text>
              ) : null}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function MetricTile({
  basis,
  label,
  hint,
  value,
  badge,
  onPress,
}: {
  basis: string;
  label: string;
  hint: string;
  value: string;
  badge?: ComparativeBadge;
  onPress: () => void;
}) {
  const { fs } = usePulseScale();
  return (
    <Pressable onPress={onPress} style={[card, { flexGrow: 1, flexBasis: basis as any, minWidth: 140 }]}>
      <Text style={quiet}>{label}</Text>
      <Text
        adjustsFontSizeToFit
        minimumFontScale={0.65}
        numberOfLines={1}
        style={{ marginTop: 6, fontFamily: Fonts.extrabold, fontSize: fs(22), color: Colors.navy }}
      >
        {value}
      </Text>
      <Text style={[quiet, { marginTop: 4 }]}>{hint}</Text>
      {badge ? (
        <Text style={{ marginTop: 6, fontFamily: Fonts.bold, fontSize: fs(12), color: badge.delta_pct < 0 ? Colors.danger : Colors.teal }}>
          {formatPct(badge.delta_pct, 0)} {badge.label}
        </Text>
      ) : null}
    </Pressable>
  );
}

function Stat({
  label,
  value,
  alert,
  onPress,
}: {
  label: string;
  value: string;
  alert?: boolean;
  onPress: () => void;
}) {
  const { fs } = usePulseScale();
  return (
    <Pressable
      onPress={() => {
        void hapticSelection();
        onPress();
      }}
      style={{
        minWidth: 72,
        flexGrow: 1,
        borderRadius: 14,
        paddingVertical: 10,
        paddingHorizontal: 8,
        backgroundColor: alert ? Colors.orangeSoft : Colors.navySoft,
        alignItems: 'center',
      }}
    >
      <Text style={{ fontFamily: Fonts.extrabold, fontSize: fs(18), color: alert ? Colors.orange : Colors.navy }}>
        {value}
      </Text>
      <Text style={{ marginTop: 2, fontFamily: Fonts.medium, fontSize: fs(11), color: Colors.muted }}>{label}</Text>
    </Pressable>
  );
}

function EmptyCard({
  title,
  body,
  action,
  onAction,
}: {
  title: string;
  body: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <View style={card}>
      <Text style={section}>{title}</Text>
      <Text style={[quiet, { marginTop: 4 }]}>{body}</Text>
      {action && onAction ? (
        <Pressable onPress={onAction} style={{ marginTop: 10 }}>
          <Text style={{ fontFamily: Fonts.bold, color: Colors.teal }}>{action}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const card = {
  backgroundColor: Colors.white,
  borderRadius: 18,
  borderWidth: 1,
  borderColor: Colors.border,
  padding: 14,
};

const officeRow = {
  flexDirection: 'row' as const,
  alignItems: 'center' as const,
  gap: 10,
  backgroundColor: Colors.white,
  borderRadius: 16,
  borderWidth: 1,
  borderColor: Colors.border,
  paddingHorizontal: 14,
  paddingVertical: 12,
};

const iconButton = {
  width: 40,
  height: 40,
  borderRadius: 14,
  alignItems: 'center' as const,
  justifyContent: 'center' as const,
  backgroundColor: Colors.white,
  borderWidth: 1,
  borderColor: Colors.border,
};

const badge = {
  position: 'absolute' as const,
  top: 4,
  right: 4,
  minWidth: 16,
  height: 16,
  borderRadius: 8,
  paddingHorizontal: 3,
  backgroundColor: Colors.orange,
  alignItems: 'center' as const,
  justifyContent: 'center' as const,
};

const section = {
  fontFamily: Fonts.bold,
  fontSize: 16,
  color: Colors.navy,
};

const quiet = {
  fontFamily: Fonts.medium,
  fontSize: 12,
  color: Colors.muted,
  lineHeight: 16,
};
