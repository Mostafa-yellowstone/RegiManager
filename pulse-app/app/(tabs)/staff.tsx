import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { useAuth } from '@/lib/auth';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { Colors, Fonts } from '@/lib/theme';

export default function TeamScreen() {
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
    <View style={{ flex: 1, backgroundColor: Colors.cream }}>
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
