import BottomSheet, {
  BottomSheetBackdrop,
  BottomSheetFlatList,
  type BottomSheetBackdropProps,
} from '@gorhom/bottom-sheet';
import { forwardRef, useCallback, useMemo } from 'react';
import { Pressable, Text, View } from 'react-native';

import { formatMoney } from '@/lib/format';
import { hapticSelection, hapticSuccess } from '@/lib/haptics';
import type { SpaceIdOrAll } from '@/types/models';

export type SpaceOption = {
  id: SpaceIdOrAll;
  name: string;
  location?: string;
  revenue?: number;
};

type Props = {
  options: SpaceOption[];
  selectedId: SpaceIdOrAll;
  onSelect: (id: SpaceIdOrAll) => void;
};

export const SpaceSwitcherSheet = forwardRef<BottomSheet, Props>(
  function SpaceSwitcherSheet({ options, selectedId, onSelect }, ref) {
    const snapPoints = useMemo(() => ['42%', '68%'], []);

    const renderBackdrop = useCallback(
      (props: BottomSheetBackdropProps) => (
        <BottomSheetBackdrop {...props} disappearsOnIndex={-1} appearsOnIndex={0} opacity={0.35} />
      ),
      [],
    );

    return (
      <BottomSheet
        ref={ref}
        index={-1}
        snapPoints={snapPoints}
        enablePanDownToClose
        backdropComponent={renderBackdrop}
        backgroundStyle={{ backgroundColor: '#FFFFFF' }}
        handleIndicatorStyle={{ backgroundColor: '#CBD5E1', width: 40 }}
      >
        <View className="px-4 pb-2">
          <Text className="text-title text-navy">Switch space</Text>
          <Text className="mt-1 text-caption text-muted">
            Filter Pulse metrics by branch or view all combined.
          </Text>
        </View>
        <BottomSheetFlatList
          data={options}
          keyExtractor={(item) => String(item.id)}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 32 }}
          renderItem={({ item }) => {
            const active = item.id === selectedId;
            return (
              <Pressable
                onPress={async () => {
                  await hapticSelection();
                  onSelect(item.id);
                  await hapticSuccess();
                }}
                className={`mb-2 rounded-2xl border px-4 py-3 ${
                  active ? 'border-navy bg-navy-soft' : 'border-border bg-white'
                }`}
                android_ripple={{ color: 'rgba(26,43,72,0.08)' }}
              >
                <View className="flex-row items-center justify-between">
                  <View className="flex-1 pr-3">
                    <Text className="text-body font-bold text-navy">{item.name}</Text>
                    {item.location ? (
                      <Text className="mt-0.5 text-caption text-muted">{item.location}</Text>
                    ) : null}
                  </View>
                  {item.revenue != null ? (
                    <Text className="text-caption font-bold text-navy">
                      {formatMoney(item.revenue, true)}
                    </Text>
                  ) : null}
                </View>
              </Pressable>
            );
          }}
        />
      </BottomSheet>
    );
  },
);

type TriggerProps = {
  label: string;
  onPress: () => void;
};

export function SpaceSwitcherTrigger({ label, onPress }: TriggerProps) {
  return (
    <Pressable
      onPress={onPress}
      className="flex-row items-center rounded-full border border-border bg-white px-3 py-2"
      android_ripple={{ color: 'rgba(26,43,72,0.1)' }}
    >
      <Text className="text-caption font-bold text-navy" numberOfLines={1}>
        {label}
      </Text>
      <Text className="ml-2 text-caption text-muted">Change</Text>
    </Pressable>
  );
}
