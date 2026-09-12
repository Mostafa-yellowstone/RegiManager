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
  color: string;
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
        tabBarActiveTintColor: Colors.primaryMid,
        tabBarInactiveTintColor: Colors.muted,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
          borderTopWidth: 1,
          height: 64,
          paddingBottom: 8,
          paddingTop: 8,
          elevation: 8,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: -2 },
          shadowOpacity: 0.04,
          shadowRadius: 8,
        },
        tabBarLabelStyle: {
          fontWeight: '600',
          fontSize: 11,
          marginTop: 2,
        },
        headerStyle: {
          backgroundColor: Colors.navy,
          elevation: 0,
          shadowOpacity: 0,
        },
        headerTintColor: Colors.white,
        headerTitleStyle: { fontWeight: '800', fontSize: 18 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Account Center',
          tabBarLabel: 'Home',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="house.fill" android="home" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="policies"
        options={{
          title: 'Policies',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="doc.text" android="description" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="id-cards"
        options={{
          title: 'Insurance ID Cards',
          tabBarLabel: 'ID Cards',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="person.crop.rectangle" android="badge" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="documents"
        options={{
          title: 'Document Vault',
          tabBarLabel: 'Documents',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="folder" android="folder" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile & Settings',
          tabBarLabel: 'Profile',
          tabBarIcon: ({ color }) => (
            <TabIcon ios="person.circle" android="person" color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="vehicles"
        options={{
          title: 'Vehicles',
          href: null,
        }}
      />
      <Tabs.Screen
        name="receipts"
        options={{
          title: 'Receipts',
          href: null,
        }}
      />
    </Tabs>
  );
}
