import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { WelcomeBand } from '@/components/pulse/WelcomeBand';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { getPulseDashboard } from '@/data/repositories/metricsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney, formatPct } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';
import { useDeskStore } from '@/stores/deskStore';

export default function TodayScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { selectedOrg, user } = useAuth();
  const setStatus = useDeskStore((s) => s.setStatus);
  const setKind = useDeskStore((s) => s.setKind);

  const dash = useQuery({
    queryKey: ['pulse-today', selectedOrg?.id],
    queryFn: () => getPulseDashboard('all', 'today', { locked: true }),
    enabled: Boolean(selectedOrg?.id),
  });

  const agentsQuery = useQuery({
    queryKey: ['pulse-agents', selectedOrg?.id],
    queryFn: () => listOwnerAgents(),
    enabled: Boolean(selectedOrg?.id),
  });

  const overview = dash.data?.overview;
  const agents = agentsQuery.data?.agents ?? [];
  const late = agents.filter((agent) => agent.is_late).length;
  const here = agents.filter((agent) => agent.attendance_open).length;
  const stillOut = agents.filter(
    (agent) => !agent.attendance_open && !agent.is_late && !agent.is_on_time,
  ).length;
  const firstName = (user?.full_name || user?.username || '').trim().split(/\s+/)[0] || '';
  const jobsToday = (overview?.records_count || 0) + (overview?.insurance_bound_count || 0);
  const leftDelta = overview?.left_delta_pct;

  function openWork() {
    void hapticSelection();
    setKind('all');
    setStatus('all');
    router.navigate('/(tabs)/sales');
  }

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 120, gap: 14 }}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          <RefreshControl
            refreshing={(dash.isFetching || agentsQuery.isFetching) && !dash.isLoading}
            onRefresh={() => {
              void hapticLight();
              void dash.refetch();
              void agentsQuery.refetch();
              void queryClient.invalidateQueries({ queryKey: ['pulse-alerts'] });
            }}
            tintColor={Colors.tealDeep}
          />
        }
      >
        {selectedOrg?.id ? <WelcomeBand name={firstName} /> : null}
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
            <SkeletonBlock height={120} />
            <SkeletonBlock height={72} />
          </View>
        ) : (
          <>
            <Pressable onPress={openWork} style={card}>
              <Text style={quiet}>Jobs today</Text>
              <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 36, color: Colors.navy }}>
                {jobsToday}
              </Text>
            </Pressable>

            <Pressable
              onPress={() => {
                void hapticSelection();
                router.navigate('/(tabs)/expenses');
              }}
              style={card}
            >
              <Text style={section}>Money</Text>
              <View style={{ flexDirection: 'row', gap: 12, marginTop: 10 }}>
                <MoneyBit label="Money in" value={formatMoney(overview.bank_income)} />
                <MoneyBit label="Money out" value={formatMoney(overview.bank_expenses)} />
                <MoneyBit label="What's left" value={formatMoney(overview.net_cash_flow)} />
              </View>
              {typeof leftDelta === 'number' ? (
                <Text style={[quiet, { marginTop: 10 }]}>
                  What's left {formatPct(leftDelta, 0)} versus yesterday
                </Text>
              ) : null}
            </Pressable>

            <Pressable
              onPress={() => {
                void hapticSelection();
                router.navigate('/(tabs)/staff');
              }}
              style={card}
            >
              <Text style={section}>Who is here</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                <Pill label={`Here ${here}`} tone="good" />
                <Pill label={`Late ${late}`} tone={late ? 'alert' : 'plain'} />
                <Pill label={`Still out ${stillOut}`} tone="plain" />
              </View>
            </Pressable>
          </>
        )}
      </ScrollView>
    </View>
  );
}

function MoneyBit({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={quiet}>{label}</Text>
      <Text style={{ marginTop: 4, fontFamily: Fonts.extrabold, fontSize: 15, color: Colors.navy }} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

function Pill({ label, tone }: { label: string; tone: 'good' | 'alert' | 'plain' }) {
  const bg = tone === 'good' ? Colors.greenSoft : tone === 'alert' ? Colors.orangeSoft : Colors.navySoft;
  const fg = tone === 'good' ? Colors.greenDeep : tone === 'alert' ? Colors.orangeDeep : Colors.navy;
  return (
    <View style={{ borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: bg }}>
      <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: fg }}>{label}</Text>
    </View>
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
          <Text style={{ fontFamily: Fonts.bold, color: Colors.tealDeep }}>{action}</Text>
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
  padding: 16,
};

const section = {
  fontFamily: Fonts.bold,
  fontSize: 16,
  color: Colors.navy,
};

const quiet = {
  fontFamily: Fonts.medium,
  fontSize: 13,
  color: Colors.muted,
  lineHeight: 18,
};
