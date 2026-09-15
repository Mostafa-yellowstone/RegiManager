import { useLocalSearchParams } from 'expo-router';
import { ScrollView, Text, View } from 'react-native';

import { formatMoney } from '@/lib/format';
import { Colors } from '@/lib/theme';

function param(value: string | string[] | undefined) {
  if (Array.isArray(value)) return value[0] || '';
  return value || '';
}

export default function ExpenseDetailScreen() {
  const params = useLocalSearchParams<{
    id: string;
    label?: string;
    amount?: string;
    category?: string;
    date?: string;
    account?: string;
    company?: string;
    transaction_type?: string;
  }>();

  const amount = Number(param(params.amount) || 0);
  const rows = [
    { label: 'Category', value: param(params.category) },
    { label: 'Date', value: param(params.date) },
    { label: 'Account', value: param(params.account) },
    { label: 'Company', value: param(params.company) },
    { label: 'Type', value: param(params.transaction_type) },
    { label: 'Reference', value: param(params.id) },
  ].filter((r) => r.value);

  return (
    <ScrollView className="flex-1 bg-cream" contentContainerStyle={{ padding: 16, gap: 12 }}>
      <View
        className="rounded-2xl bg-white p-5"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        <Text className="text-[11px] font-bold uppercase tracking-wide text-muted">
          Bank expense
        </Text>
        <Text className="mt-2 text-[22px] font-extrabold text-navy">
          {param(params.label) || 'Expense'}
        </Text>
        <Text className="mt-3 text-[32px] font-extrabold text-teal">
          {formatMoney(Number.isFinite(amount) ? amount : 0)}
        </Text>
      </View>

      <View
        className="rounded-2xl bg-white p-4"
        style={{ borderWidth: 1, borderColor: Colors.border }}
      >
        {rows.map((row) => (
          <View
            key={row.label}
            className="flex-row items-start justify-between py-2"
            style={{ borderBottomWidth: 1, borderBottomColor: Colors.border }}
          >
            <Text className="text-caption font-bold text-muted">{row.label}</Text>
            <Text className="ml-4 flex-1 text-right text-body font-semibold text-navy">
              {row.value}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
