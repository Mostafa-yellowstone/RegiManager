import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { DateRangeSelector } from '@/components/pulse/DateRangeSelector';
import { MetricCard } from '@/components/pulse/MetricCard';
import { MetricGrid } from '@/components/pulse/MetricGrid';
import { SkeletonBlock } from '@/components/pulse/SkeletonBlock';
import { getInsuranceSummary } from '@/data/repositories/insuranceRepository';
import { useAuth } from '@/lib/auth';
import { crmInsuranceUrl, openCrmUrl } from '@/lib/crmLinks';
import { formatMoney } from '@/lib/format';
import { hapticLight, hapticSelection } from '@/lib/haptics';
import { buildInsuranceRecommendations } from '@/lib/insuranceInsights';
import { Colors, Fonts } from '@/lib/theme';
import { useDateRangeStore } from '@/stores/dateRangeStore';
import type { DateRangePreset } from '@/types/models';

function levelTone(level: 'critical' | 'warning' | 'info') {
  if (level === 'critical') return { bg: '#FEE2E2', fg: '#991B1B' };
  if (level === 'warning') return { bg: Colors.orangeSoft, fg: Colors.orangeDeep };
  return { bg: Colors.tealSoft, fg: Colors.tealDeep };
}

export default function InsuranceScreen() {
  const insets = useSafeAreaInsets();
  const { selectedOrg } = useAuth();
  const preset = useDateRangeStore((s) => s.preset);
  const setPreset = useDateRangeStore((s) => s.setPreset);

  const { data, isLoading, isFetching, refetch, isError, error } = useQuery({
    queryKey: ['pulse-insurance', selectedOrg?.id, preset],
    queryFn: () => getInsuranceSummary(preset),
    enabled: Boolean(selectedOrg?.id),
  });

  const recommendations = useMemo(() => buildInsuranceRecommendations(data), [data]);

  function onRangeChange(next: DateRangePreset) {
    setPreset(next);
  }

  const totals = data?.totals;

  return (
    <View style={{ flex: 1, backgroundColor: Colors.cream, paddingTop: insets.top }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 120, gap: 16 }}
        refreshControl={
          <RefreshControl
            refreshing={isFetching && !isLoading}
            onRefresh={() => {
              void hapticLight();
              void refetch();
            }}
            tintColor={Colors.teal}
          />
        }
      >
        <View style={{ gap: 8 }}>
          <Text style={{ fontFamily: Fonts.extrabold, fontSize: 28, color: Colors.navy, letterSpacing: -0.4 }}>
            Insurance
          </Text>
          <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted, lineHeight: 18 }}>
            Earned vs unearned commission, premium by carrier, and owner recommendations.
          </Text>
          <DateRangeSelector value={preset} onChange={onRangeChange} />
        </View>

        {isError ? (
          <View
            style={{
              borderRadius: 16,
              borderWidth: 1,
              borderColor: 'rgba(220,38,38,0.3)',
              backgroundColor: Colors.white,
              padding: 16,
            }}
          >
            <Text style={{ fontFamily: Fonts.bold, color: Colors.danger }}>Could not load insurance</Text>
            <Text style={{ marginTop: 4, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
              {(error as Error)?.message || 'Check connection and insurance access.'}
            </Text>
            <Pressable style={{ marginTop: 12 }} onPress={() => void refetch()}>
              <Text style={{ fontFamily: Fonts.semibold, color: Colors.teal }}>Retry</Text>
            </Pressable>
          </View>
        ) : null}

        {isLoading || !data ? (
          <View style={{ gap: 12 }}>
            <SkeletonBlock height={120} />
            <SkeletonBlock height={120} />
            <SkeletonBlock height={180} />
          </View>
        ) : !data.available ? (
          <View
            style={{
              borderRadius: 16,
              backgroundColor: Colors.white,
              padding: 16,
              borderWidth: 1,
              borderColor: Colors.border,
            }}
          >
            <Text style={{ fontFamily: Fonts.bold, fontSize: 16, color: Colors.navy }}>
              Insurance not available
            </Text>
            <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
              This PSB does not have Insurance space access for your account.
            </Text>
          </View>
        ) : (
          <>
            <View style={{ gap: 10 }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 18, color: Colors.navy }}>Commissions</Text>
              <MetricGrid>
                <MetricCard
                  label="Earned"
                  value={totals?.earned_commission || 0}
                  accent="green"
                  hint="Outstanding earned book"
                />
                <MetricCard
                  label="Unearned"
                  value={totals?.unearned_commission || 0}
                  accent="orange"
                  hint="Still to earn / chase"
                />
                <MetricCard
                  label="Received"
                  value={totals?.received_commission || 0}
                  accent="teal"
                  hint="Already remitted"
                />
                <MetricCard
                  label="Broker fee"
                  value={totals?.period_broker_fee || 0}
                  accent="teal"
                  hint="Period broker fees"
                  metaLabel="binds"
                  metaValue={totals?.period_bound_count || 0}
                />
              </MetricGrid>
            </View>

            <View style={{ gap: 10 }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 18, color: Colors.navy }}>Premium</Text>
              <View
                style={{
                  borderRadius: 16,
                  backgroundColor: Colors.white,
                  padding: 16,
                  borderWidth: 1,
                  borderColor: Colors.border,
                }}
              >
                <Text
                  style={{
                    fontFamily: Fonts.bold,
                    fontSize: 11,
                    letterSpacing: 0.6,
                    textTransform: 'uppercase',
                    color: Colors.tealDeep,
                  }}
                >
                  Total premium (range)
                </Text>
                <Text
                  style={{
                    marginTop: 8,
                    fontFamily: Fonts.extrabold,
                    fontSize: 28,
                    color: Colors.navy,
                  }}
                >
                  {formatMoney(totals?.period_premium || 0)}
                </Text>
                <Text style={{ marginTop: 6, fontFamily: Fonts.medium, fontSize: 12, color: Colors.muted }}>
                  Active book premium {formatMoney(totals?.book_premium || 0)} ·{' '}
                  {totals?.active_policy_count || 0} active policies · {totals?.period_bound_count || 0}{' '}
                  binds in range
                </Text>
              </View>
            </View>

            <View style={{ gap: 10 }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 18, color: Colors.navy }}>
                Premium by company
              </Text>
              {(data.companies || []).length === 0 ? (
                <View
                  style={{
                    borderRadius: 16,
                    backgroundColor: Colors.white,
                    padding: 16,
                    borderWidth: 1,
                    borderColor: Colors.border,
                  }}
                >
                  <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted }}>
                    No carriers with activity for this organization yet.
                  </Text>
                </View>
              ) : (
                <View style={{ gap: 8 }}>
                  {data.companies.map((company) => (
                    <View
                      key={company.id}
                      style={{
                        borderRadius: 16,
                        backgroundColor: Colors.white,
                        paddingHorizontal: 16,
                        paddingVertical: 14,
                        borderWidth: 1,
                        borderColor: Colors.border,
                      }}
                    >
                      <View
                        style={{
                          flexDirection: 'row',
                          alignItems: 'flex-start',
                          justifyContent: 'space-between',
                          gap: 12,
                        }}
                      >
                        <View style={{ flex: 1, minWidth: 0 }}>
                          <Text
                            numberOfLines={1}
                            style={{ fontFamily: Fonts.bold, fontSize: 15, color: Colors.navy }}
                          >
                            {company.name}
                          </Text>
                          <Text
                            style={{
                              marginTop: 4,
                              fontFamily: Fonts.medium,
                              fontSize: 12,
                              color: Colors.muted,
                            }}
                          >
                            {company.active_count} active · {company.period_bound_count} binds in range
                          </Text>
                        </View>
                        <Text style={{ fontFamily: Fonts.extrabold, fontSize: 16, color: Colors.teal }}>
                          {formatMoney(company.period_premium)}
                        </Text>
                      </View>
                      <View
                        style={{
                          marginTop: 10,
                          flexDirection: 'row',
                          flexWrap: 'wrap',
                          gap: 8,
                        }}
                      >
                        <View
                          style={{
                            borderRadius: 999,
                            paddingHorizontal: 10,
                            paddingVertical: 5,
                            backgroundColor: Colors.greenSoft,
                          }}
                        >
                          <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.greenDeep }}>
                            Earned {formatMoney(company.earned_commission, true)}
                          </Text>
                        </View>
                        <View
                          style={{
                            borderRadius: 999,
                            paddingHorizontal: 10,
                            paddingVertical: 5,
                            backgroundColor: Colors.orangeSoft,
                          }}
                        >
                          <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.orangeDeep }}>
                            Unearned {formatMoney(company.unearned_commission, true)}
                          </Text>
                        </View>
                        <View
                          style={{
                            borderRadius: 999,
                            paddingHorizontal: 10,
                            paddingVertical: 5,
                            backgroundColor: Colors.tealSoft,
                          }}
                        >
                          <Text style={{ fontFamily: Fonts.bold, fontSize: 11, color: Colors.tealDeep }}>
                            Book {formatMoney(company.book_premium, true)}
                          </Text>
                        </View>
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </View>

            <View style={{ gap: 10 }}>
              <Text style={{ fontFamily: Fonts.bold, fontSize: 18, color: Colors.navy }}>
                Recommendations
              </Text>
              <View style={{ gap: 8 }}>
                {recommendations.map((item) => {
                  const tone = levelTone(item.level);
                  return (
                    <View
                      key={item.id}
                      style={{
                        borderRadius: 16,
                        backgroundColor: Colors.white,
                        padding: 14,
                        borderWidth: 1,
                        borderColor: Colors.border,
                      }}
                    >
                      <View
                        style={{
                          flexDirection: 'row',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 8,
                          marginBottom: 6,
                        }}
                      >
                        <Text
                          style={{
                            flex: 1,
                            fontFamily: Fonts.bold,
                            fontSize: 15,
                            color: Colors.navy,
                          }}
                        >
                          {item.title}
                        </Text>
                        <View
                          style={{
                            borderRadius: 999,
                            paddingHorizontal: 8,
                            paddingVertical: 3,
                            backgroundColor: tone.bg,
                          }}
                        >
                          <Text style={{ fontFamily: Fonts.extrabold, fontSize: 10, color: tone.fg }}>
                            {item.level === 'critical'
                              ? 'Urgent'
                              : item.level === 'warning'
                                ? 'Watch'
                                : 'Tip'}
                          </Text>
                        </View>
                      </View>
                      <Text style={{ fontFamily: Fonts.medium, fontSize: 13, color: Colors.muted, lineHeight: 18 }}>
                        {item.body}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </View>

            <Pressable
              onPress={() => {
                void hapticSelection();
                void openCrmUrl(crmInsuranceUrl());
              }}
              style={{
                alignSelf: 'flex-start',
                paddingVertical: 8,
              }}
            >
              <Text style={{ fontFamily: Fonts.bold, fontSize: 13, color: Colors.teal }}>
                Open Insurance in CRM →
              </Text>
            </Pressable>
          </>
        )}
      </ScrollView>
    </View>
  );
}
