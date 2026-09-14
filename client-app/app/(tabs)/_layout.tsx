import { SymbolView } from 'expo-symbols';
import { Tabs } from 'expo-router';

import { Colors } from '@/constants/theme';

function TabIcon({
  ios,
  android,
  color,
}: {
  ios: string;
  android: string;
  color: any;
}) {
  return (
    <SymbolView
      name={{ ios: ios as any, android: android as any, web: android as any }}
      tintColor={color}
      size={24}
    />
  );
}

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors.navy,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontWeight: '700', fontSize: 11 },
        headerStyle: { backgroundColor: Colors.navy },
        headerTintColor: Colors.white,
        headerTitleStyle: { fontWeight: '800', fontSize: 16, letterSpacing: 0.3 },
        headerTitle: 'REGIMANAGER WALLET',
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'REGIMANAGER WALLET',
          tabBarLabel: 'Home',
          tabBarIcon: ({ color }) => <TabIcon ios="house.fill" android="home" color={color} />,
        }}
      />
      <Tabs.Screen
        name="policies"
        options={{
          title: 'Wallet',
          tabBarLabel: 'Wallet',
          tabBarIcon: ({ color }) => <TabIcon ios="creditcard.fill" android="account_balance_wallet" color={color} />,
        }}
      />
      <Tabs.Screen
        name="vehicles"
        options={{
          title: 'Vehicles',
          tabBarLabel: 'Vehicles',
          tabBarIcon: ({ color }) => <TabIcon ios="car.fill" android="directions_car" color={color} />,
        }}
      />
      <Tabs.Screen
        name="chat"
        options={{
          title: 'Agent',
          tabBarLabel: 'Agent',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="bubble.left.and.bubble.right.fill" android="chat" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="services"
        options={{
          title: 'Services',
          href: null,
        }}
      />
      <Tabs.Screen name="receipts" options={{ title: 'Receipts', href: null }} />
      <Tabs.Screen name="id-cards" options={{ title: 'ID Cards', href: null }} />
      <Tabs.Screen name="documents" options={{ title: 'Document Vault', href: null }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile', href: null }} />
    </Tabs>
  );
}
