import { useLocalSearchParams } from 'expo-router';
import { ScrollView, Text, View } from 'react-native';

import { jobStatusLabel } from '@/data/repositories/workRepository';
import { formatMoney } from '@/lib/format';
import { Colors, Fonts } from '@/lib/theme';

function param(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || '';
  return value || '';
}

export default function JobScreen() {
  const params = useLocalSearchParams<{
    id: string;
    title?: string;
    customer?: string;
    person?: string;
    status?: string;
    kind?: string;
    amount?: string;
    date?: string;
    detail?: string;
  }>();

  const status = jobStatusLabel(param(params.status));
  const amount = Number(param(params.amount) || 0);
  const person = param(params.person);
  const next =
    status === 'Waiting'
      ? 'Waiting on the desk'
      : status === 'Needs you'
        ? 'Needs a person to pick it up'
        : status === 'Done'
          ? 'Done'
          : status === 'Refunded'
            ? 'Refunded'
            : status || 'Open';

  const rows = [
    { label: 'Kind', value: param(params.kind) },
    { label: 'Customer', value: param(params.customer) },
    { label: 'Person', value: person || 'Unassigned' },
    { label: 'When', value: param(params.date) },
    { label: 'Status', value: status },
    { label: 'Next step', value: next },
    { label: 'Reference', value: param(params.detail) },
    { label: 'Amount', value: amount ? formatMoney(amount) : '' },
  ].filter((row) => row.value);

  return (
    <ScrollView style={{ flex: 1, backgroundColor: Colors.cream }} contentContainerStyle={{ padding: 16, gap: 12 }}>
      <Text style={{ fontFamily: Fonts.extrabold, fontSize: 26, color: Colors.navy, letterSpacing: -0.4 }}>
        {param(params.title) || 'Job'}
      </Text>
      <View
        style={{
          backgroundColor: Colors.white,
          borderRadius: 16,
          borderWidth: 1,
          borderColor: Colors.border,
          padding: 16,
          gap: 12,
        }}
      >
        {rows.map((row) => (
          <View key={row.label}>
            <Text style={{ fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>{row.label}</Text>
            <Text style={{ marginTop: 2, fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>{row.value}</Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
