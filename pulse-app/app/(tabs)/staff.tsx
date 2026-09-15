import { useQuery } from '@tanstack/react-query';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { AttendanceStrip } from '@/components/pulse/AttendanceStrip';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { listOwnerAgents } from '@/data/repositories/agentsRepository';
import { useAuth } from '@/lib/auth';
import { formatMoney } from '@/lib/format';
import { hapticLight } from '@/lib/haptics';
import { Colors } from '@/lib/theme';

export default function StaffScreen() {
  const { selectedOrg } = useAuth();
  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-agents', selectedOrg?.id],
    queryFn: () => listOwnerAgents(),
    enabled: Boolean(selectedOrg?.id),
  });

  return (
    <ScrollView
      className="flex-1 bg-cream"
      contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
      refreshControl={
        <RefreshControl
          refreshing={isFetching && !isLoading}
          onRefresh={() => {
            void hapticLight();
            void refetch();
          }}
          tintColor="#1A2B48"
        />
      }
    >
      <Text className="text-title text-navy">Staff attendance</Text>
      <Text className="mb-2 text-caption text-muted">
        Egypt team start 4:00 PM · after 4:00 PM Egypt = late · work day{' '}
        {data?.work_date || 'today'} (NY)
      </Text>

      {isError ? (
        <Text className="text-caption font-semibold text-danger">
          {(error as Error)?.message || 'Owner access required for staff roster'}
        </Text>
      ) : null}

      {isLoading ? (
        <>
          <SkeletonBlock height={88} />
          <SkeletonBlock height={88} />
        </>
      ) : (data?.agents.length ?? 0) === 0 ? (
        <Text className="mt-6 text-center text-body text-muted">No agents found.</Text>
      ) : (
        <>
          <AttendanceStrip agents={data?.agents ?? []} workDate={data?.work_date} />
          {data?.agents.map((agent) => (
            <View
              key={agent.membership_id}
              className="rounded-2xl border border-border bg-white px-4 py-3"
            >
              <View className="flex-row items-center justify-between">
                <View className="flex-1 pr-3">
                  <Text className="text-body font-bold text-navy">{agent.name}</Text>
                  <Text className="mt-0.5 text-caption text-muted">{agent.role}</Text>
                </View>
                <View className="flex-row gap-2">
                  {agent.is_late ? (
                    <View
                      className="rounded-full px-2.5 py-1"
                      style={{ backgroundColor: Colors.orangeSoft }}
                    >
                      <Text className="text-caption font-bold" style={{ color: Colors.orangeDeep }}>
                        Late
                      </Text>
                    </View>
                  ) : null}
                  {agent.is_on_time ? (
                    <View
                      className="rounded-full px-2.5 py-1"
                      style={{ backgroundColor: Colors.greenSoft }}
                    >
                      <Text className="text-caption font-bold" style={{ color: Colors.greenDeep }}>
                        On time
                      </Text>
                    </View>
                  ) : null}
                  <View
                    className={`rounded-full px-2.5 py-1 ${
                      agent.attendance_open ? 'bg-success/15' : 'bg-navy-soft'
                    }`}
                  >
                    <Text
                      className={`text-caption font-bold ${
                        agent.attendance_open ? 'text-success' : 'text-muted'
                      }`}
                    >
                      {agent.attendance_open ? 'On duty' : 'Off'}
                    </Text>
                  </View>
                </View>
              </View>
              <Text className="mt-2 text-caption text-navy">{agent.attendance_label}</Text>
              {(agent.started_at || agent.ended_at) && (
                <View className="mt-2 flex-row justify-between">
                  <Text className="text-caption text-muted">
                    Started {agent.started_at || '—'}
                  </Text>
                  <Text className="text-caption text-muted">
                    Ended {agent.ended_at || (agent.attendance_open ? 'still open' : '—')}
                  </Text>
                </View>
              )}
              <View className="mt-3 flex-row justify-between">
                <Text className="text-caption text-muted">Tasks {agent.task_percent}%</Text>
                <Text className="text-caption font-semibold text-navy">
                  {agent.service_records_total} records ·{' '}
                  {formatMoney(agent.service_revenue_total, true)}
                </Text>
              </View>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}
