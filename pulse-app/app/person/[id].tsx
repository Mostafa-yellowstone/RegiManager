import { useQuery } from '@tanstack/react-query';
import { useLocalSearchParams } from 'expo-router';
import { ScrollView, Text, View } from 'react-native';

import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { fetchOwnerAgentWorkboard } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { Colors, Fonts } from '@/lib/theme';

function param(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || '';
  return value || '';
}

export default function PersonScreen() {
  const { selectedOrg } = useAuth();
  const params = useLocalSearchParams<{
    id: string;
    name?: string;
    role?: string;
    late?: string;
    here?: string;
    label?: string;
    jobs?: string;
  }>();
  const membershipId = Number(param(params.id));

  const board = useQuery({
    queryKey: ['pulse-person', selectedOrg?.id, membershipId],
    queryFn: () => fetchOwnerAgentWorkboard(membershipId),
    enabled: Boolean(selectedOrg?.id) && Number.isFinite(membershipId),
  });

  const name = board.data?.agent?.full_name || board.data?.agent?.name || param(params.name) || 'Person';
  const late = param(params.late) === '1' || board.data?.attendance?.is_late;
  const here = param(params.here) === '1' || board.data?.attendance?.is_open;
  const presence = late ? 'Late' : here ? 'Here' : 'Out';
  const activity = board.data?.recent_activity || board.data?.today_activity || [];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: Colors.cream }} contentContainerStyle={{ padding: 16, gap: 12 }}>
      <Text style={{ fontFamily: Fonts.extrabold, fontSize: 26, color: Colors.navy }}>{name}</Text>
      <Text style={{ fontFamily: Fonts.medium, fontSize: 14, color: Colors.muted }}>
        {[presence, param(params.label), param(params.jobs) ? `${param(params.jobs)} jobs` : '']
          .filter(Boolean)
          .join(' · ')}
      </Text>
      {board.isLoading ? <SkeletonBlock height={120} /> : null}
      {board.isError ? (
        <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
          {(board.error as Error)?.message || 'This roster card is all that is open right now.'}
        </Text>
      ) : null}
      {activity.map((item: any) => (
        <View
          key={String(item.id)}
          style={{
            backgroundColor: Colors.white,
            borderRadius: 16,
            borderWidth: 1,
            borderColor: Colors.border,
            padding: 14,
            gap: 4,
          }}
        >
          <Text style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}>{item.title || 'Work'}</Text>
          {item.detail ? (
            <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>{item.detail}</Text>
          ) : null}
          <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
            {item.created_at ? String(item.created_at).slice(0, 16).replace('T', ' ') : ''}
          </Text>
        </View>
      ))}
    </ScrollView>
  );
}
