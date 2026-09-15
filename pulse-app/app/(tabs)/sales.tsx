import { Text, View } from 'react-native';

export default function SalesScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-cream px-8">
      <Text className="text-title text-navy">Sales tracking</Text>
      <Text className="mt-2 text-center text-body text-muted">
        View service revenue and ticket trends here. Owners do not create sales in Pulse.
      </Text>
    </View>
  );
}
