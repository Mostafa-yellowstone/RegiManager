import { Pressable, Text, View } from 'react-native';

import { formatMoney, formatPct } from '@/lib/format';
import { Colors } from '@/lib/theme';
import type { MorningBriefModel } from '@/lib/ownerInsights';

type Props = {
  brief: MorningBriefModel;
  onOpenStaff?: () => void;
  onOpenExpenses?: () => void;
};

export function MorningBrief({ brief, onOpenStaff, onOpenExpenses }: Props) {
  return (
    <View
      className="overflow-hidden rounded-3xl"
      style={{
        backgroundColor: Colors.navy,
        borderWidth: 1,
        borderColor: '#164E63',
      }}
    >
      <View className="px-4 pb-4 pt-4">
        <Text className="text-[11px] font-extrabold uppercase tracking-[1.5px] text-teal">
          Morning brief
        </Text>
        <Text className="mt-1 text-caption" style={{ color: 'rgba(255,255,255,0.65)' }}>
          {brief.asOfLabel}
          {brief.workDate ? ` · staff ${brief.workDate}` : ''}
        </Text>

        <View className="mt-4 flex-row gap-3">
          <View className="flex-1 rounded-2xl px-3 py-3" style={{ backgroundColor: 'rgba(13,148,136,0.18)' }}>
            <Text className="text-[10px] font-bold uppercase" style={{ color: '#99F6E4' }}>
              Profit
            </Text>
            <Text className="mt-1 text-[22px] font-extrabold text-white">
              {formatMoney(brief.netProfit)}
            </Text>
            {brief.profitBadge ? (
              <Text className="mt-1 text-[11px] font-semibold" style={{ color: '#5EEAD4' }}>
                {formatPct(brief.profitBadge.delta_pct)} {brief.profitBadge.label}
              </Text>
            ) : (
              <Text className="mt-1 text-[11px]" style={{ color: 'rgba(255,255,255,0.5)' }}>
                Ins + DMV
              </Text>
            )}
          </View>
          <View className="flex-1 rounded-2xl px-3 py-3" style={{ backgroundColor: 'rgba(201,162,39,0.16)' }}>
            <Text className="text-[10px] font-bold uppercase" style={{ color: '#F7E7A1' }}>
              Cash flow
            </Text>
            <Text className="mt-1 text-[22px] font-extrabold text-white">
              {formatMoney(brief.cashFlow)}
            </Text>
            <Text className="mt-1 text-[11px]" style={{ color: 'rgba(255,255,255,0.5)' }}>
              Bank income − exp
            </Text>
          </View>
        </View>

        <View className="mt-3 flex-row gap-2">
          <Pressable
            onPress={onOpenStaff}
            className="flex-1 rounded-xl px-3 py-2.5"
            style={{ backgroundColor: 'rgba(255,255,255,0.08)' }}
          >
            <Text className="text-[10px] font-bold uppercase" style={{ color: 'rgba(255,255,255,0.55)' }}>
              Staff today
            </Text>
            <Text className="mt-0.5 text-caption font-bold text-white">
              {brief.onDuty} on duty · {brief.onTime} on time · {brief.late} late
            </Text>
          </Pressable>
          <Pressable
            onPress={onOpenExpenses}
            className="rounded-xl px-3 py-2.5"
            style={{ backgroundColor: 'rgba(255,255,255,0.08)', minWidth: 108 }}
          >
            <Text className="text-[10px] font-bold uppercase" style={{ color: 'rgba(255,255,255,0.55)' }}>
              Expenses
            </Text>
            <Text className="mt-0.5 text-caption font-bold text-white">
              {formatMoney(brief.bankExpenses, true)}
            </Text>
            {brief.expenseBadge ? (
              <Text className="mt-0.5 text-[10px] font-semibold" style={{ color: '#FDBA74' }}>
                {formatPct(brief.expenseBadge.delta_pct)}
              </Text>
            ) : null}
          </Pressable>
        </View>
      </View>
    </View>
  );
}
