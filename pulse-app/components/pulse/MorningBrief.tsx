import { Pressable, Text, View } from 'react-native';

import { formatMoney, formatPct } from '@/lib/format';
import { Colors, Fonts } from '@/lib/theme';
import type { MorningBriefModel } from '@/lib/ownerInsights';

type Props = {
  brief: MorningBriefModel;
  onOpenStaff?: () => void;
  onOpenExpenses?: () => void;
};

export function MorningBrief({ brief, onOpenStaff, onOpenExpenses }: Props) {
  return (
    <View
      style={{
        overflow: 'hidden',
        borderRadius: 24,
        backgroundColor: Colors.navy,
        borderWidth: 1,
        borderColor: Colors.navyMid,
      }}
    >
      <View style={{ paddingHorizontal: 16, paddingBottom: 16, paddingTop: 16 }}>
        <Text
          style={{
            fontFamily: Fonts.extrabold,
            fontSize: 11,
            letterSpacing: 1.5,
            textTransform: 'uppercase',
            color: Colors.teal,
          }}
        >
          Morning brief
        </Text>
        <Text
          style={{
            marginTop: 4,
            fontFamily: Fonts.medium,
            fontSize: 12,
            color: 'rgba(255,255,255,0.65)',
          }}
        >
          {brief.asOfLabel}
          {brief.workDate ? ` · staff ${brief.workDate}` : ''}
        </Text>

        <View style={{ marginTop: 16, flexDirection: 'row', gap: 12 }}>
          <View
            style={{
              flex: 1,
              borderRadius: 16,
              paddingHorizontal: 12,
              paddingVertical: 12,
              backgroundColor: 'rgba(13,148,136,0.18)',
            }}
          >
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 10,
                textTransform: 'uppercase',
                color: '#99F6E4',
              }}
            >
              Net profit
            </Text>
            <Text
              style={{
                marginTop: 4,
                fontFamily: Fonts.extrabold,
                fontSize: 22,
                color: '#FFFFFF',
              }}
            >
              {formatMoney(brief.netProfit)}
            </Text>
            <Text
              style={{
                marginTop: 4,
                fontFamily: Fonts.semibold,
                fontSize: 11,
                color: 'rgba(255,255,255,0.55)',
              }}
            >
              {brief.profitHint}
            </Text>
            {brief.profitBadge ? (
              <Text
                style={{
                  marginTop: 4,
                  fontFamily: Fonts.semibold,
                  fontSize: 11,
                  color: '#5EEAD4',
                }}
              >
                {formatPct(brief.profitBadge.delta_pct)} {brief.profitBadge.label}
              </Text>
            ) : null}
          </View>
          <View
            style={{
              flex: 1,
              borderRadius: 16,
              paddingHorizontal: 12,
              paddingVertical: 12,
              backgroundColor: 'rgba(201,162,39,0.16)',
            }}
          >
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 10,
                textTransform: 'uppercase',
                color: '#F7E7A1',
              }}
            >
              Cash flow
            </Text>
            <Text
              style={{
                marginTop: 4,
                fontFamily: Fonts.extrabold,
                fontSize: 22,
                color: '#FFFFFF',
              }}
            >
              {formatMoney(brief.cashFlow)}
            </Text>
            <Text
              style={{
                marginTop: 4,
                fontFamily: Fonts.medium,
                fontSize: 11,
                color: 'rgba(255,255,255,0.5)',
              }}
            >
              Bank income − exp
            </Text>
          </View>
        </View>

        <View style={{ marginTop: 12, flexDirection: 'row', gap: 8 }}>
          <Pressable
            onPress={onOpenStaff}
            style={{
              flex: 1,
              borderRadius: 12,
              paddingHorizontal: 12,
              paddingVertical: 10,
              backgroundColor: 'rgba(255,255,255,0.08)',
            }}
          >
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 10,
                textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.55)',
              }}
            >
              Staff today
            </Text>
            <Text style={{ marginTop: 2, fontFamily: Fonts.bold, fontSize: 12, color: '#FFFFFF' }}>
              {brief.onDuty} on duty · {brief.onTime} on time · {brief.late} late
            </Text>
          </Pressable>
          <Pressable
            onPress={onOpenExpenses}
            style={{
              borderRadius: 12,
              paddingHorizontal: 12,
              paddingVertical: 10,
              backgroundColor: 'rgba(255,255,255,0.08)',
              minWidth: 108,
            }}
          >
            <Text
              style={{
                fontFamily: Fonts.bold,
                fontSize: 10,
                textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.55)',
              }}
            >
              Expenses
            </Text>
            <Text style={{ marginTop: 2, fontFamily: Fonts.bold, fontSize: 12, color: '#FFFFFF' }}>
              {formatMoney(brief.bankExpenses, true)}
            </Text>
            {brief.expenseBadge ? (
              <Text
                style={{
                  marginTop: 2,
                  fontFamily: Fonts.semibold,
                  fontSize: 10,
                  color: '#FDBA74',
                }}
              >
                {formatPct(brief.expenseBadge.delta_pct)}
              </Text>
            ) : null}
          </Pressable>
        </View>
      </View>
    </View>
  );
}
