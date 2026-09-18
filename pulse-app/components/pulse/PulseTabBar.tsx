import { Pressable, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PulseTabIcon } from '@/components/pulse/PulseTabIcon';
import { Colors, Fonts } from '@/lib/theme';

type TabKey = 'pulse' | 'sales' | 'staff' | 'expenses';

type Props = {
  state: { index: number; routes: Array<{ key: string; name: string }> };
  descriptors: Record<string, { options: any }>;
  navigation: any;
};

const ORDER: TabKey[] = ['pulse', 'sales', 'staff', 'expenses'];
const LABELS: Record<TabKey, string> = {
  pulse: 'Pulse',
  sales: 'Sales',
  staff: 'Staff',
  expenses: 'Expenses',
};

function routeToTab(name: string): TabKey {
  if (name === 'index') return 'pulse';
  if (name === 'sales' || name === 'staff' || name === 'expenses') return name;
  return 'pulse';
}

export function PulseTabBar({ state, descriptors, navigation }: Props) {
  const insets = useSafeAreaInsets();

  return (
    <View
      style={{
        paddingBottom: Math.max(insets.bottom, 10),
        paddingTop: 10,
        paddingHorizontal: 12,
        backgroundColor: Colors.white,
        borderTopWidth: 1,
        borderTopColor: Colors.border,
      }}
    >
      <View
        style={{
          flexDirection: 'row',
          gap: 8,
          backgroundColor: Colors.navySoft,
          borderRadius: 18,
          padding: 6,
        }}
      >
        {state.routes.map((route, index) => {
          const focused = state.index === index;
          const tab = routeToTab(route.name);
          if (!ORDER.includes(tab) && route.name !== 'index') {
            // hide non-primary routes if any
          }
          const { options } = descriptors[route.key];
          const label = LABELS[tab] || options.title || route.name;

          const onPress = () => {
            const event = navigation.emit({
              type: 'tabPress',
              target: route.key,
              canPreventDefault: true,
            });
            if (!focused && !event.defaultPrevented) {
              navigation.navigate(route.name);
            }
          };

          return (
            <Pressable
              key={route.key}
              onPress={onPress}
              accessibilityRole="button"
              accessibilityState={focused ? { selected: true } : {}}
              style={{
                flex: 1,
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 14,
                paddingVertical: 8,
                paddingHorizontal: 4,
                backgroundColor: focused ? Colors.white : 'transparent',
                shadowColor: focused ? '#0B3D3A' : 'transparent',
                shadowOpacity: focused ? 0.08 : 0,
                shadowRadius: 8,
                shadowOffset: { width: 0, height: 2 },
                elevation: focused ? 2 : 0,
              }}
            >
              <View style={{ alignItems: 'center', gap: 4 }}>
                <PulseTabIcon name={tab} focused={focused} compact />
                <Text
                  style={{
                    fontFamily: Fonts.bold,
                    fontSize: 11,
                    color: focused ? Colors.teal : Colors.muted,
                  }}
                >
                  {label}
                </Text>
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
