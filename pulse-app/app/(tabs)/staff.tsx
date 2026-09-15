import { Text, View } from 'react-native';

export default function StaffScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-cream px-8">
      <Text className="text-title text-navy">Staff tracking</Text>
      <Text className="mt-2 text-center text-body text-muted">
        Monitor attendance and performance. Owners do not clock staff in from Pulse.
      </Text>
    </View>
  );
}
