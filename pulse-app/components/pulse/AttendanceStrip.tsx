import { Pressable, ScrollView, Text, View } from 'react-native';

import { Colors } from '@/lib/theme';
import type { AgentRosterRow } from '@/types/models';

type Props = {
  agents: AgentRosterRow[];
  workDate?: string;
  onSeeAll?: () => void;
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function statusColor(agent: AgentRosterRow) {
  if (agent.is_late) return Colors.orange;
  if (agent.is_on_time) return Colors.green;
  if (agent.attendance_open) return Colors.teal;
  return Colors.muted;
}

function statusLabel(agent: AgentRosterRow) {
  if (agent.is_late) return 'Late';
  if (agent.is_on_time) return 'On time';
  if (agent.attendance_open) return 'In';
  return 'Off';
}

export function AttendanceStrip({ agents, workDate, onSeeAll }: Props) {
  if (!agents.length) return null;

  const onDuty = agents.filter((a) => a.attendance_open).length;
  const onTime = agents.filter((a) => a.is_on_time).length;
  const late = agents.filter((a) => a.is_late).length;

  return (
    <View
      className="rounded-2xl bg-white p-3"
      style={{
        borderWidth: 1,
        borderColor: Colors.border,
        shadowColor: '#0F3D4C',
        shadowOpacity: 0.05,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 2 },
        elevation: 1,
      }}
    >
      <View className="mb-2 flex-row items-center justify-between">
        <View className="flex-1 pr-2">
          <Text className="text-title text-navy">Staff today</Text>
          <Text className="text-caption text-muted">
            {onDuty} on duty
            {onTime ? ` · ${onTime} on time` : ''}
            {late ? ` · ${late} late` : ''}
            {workDate ? ` · ${workDate}` : ''}
          </Text>
          <Text className="mt-0.5 text-[10px] text-muted">
            After 9:00 AM New York = late · at/before 9:00 = on time
          </Text>
        </View>
        {onSeeAll ? (
          <Pressable onPress={onSeeAll}>
            <Text className="text-caption font-bold text-teal">See all</Text>
          </Pressable>
        ) : null}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
        {agents.map((agent) => {
          const color = statusColor(agent);
          return (
            <View key={agent.membership_id} style={{ width: 72, alignItems: 'center' }}>
              <View
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 22,
                  backgroundColor: Colors.cream,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderWidth: 2,
                  borderColor: color,
                }}
              >
                <Text style={{ fontWeight: '800', color: Colors.navy, fontSize: 13 }}>
                  {initials(agent.name)}
                </Text>
              </View>
              <Text
                numberOfLines={1}
                style={{ marginTop: 6, fontSize: 11, fontWeight: '700', color: Colors.navy }}
              >
                {agent.name.split(' ')[0]}
              </Text>
              <Text style={{ fontSize: 10, fontWeight: '700', color }}>{statusLabel(agent)}</Text>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}
