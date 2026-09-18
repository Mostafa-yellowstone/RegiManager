import { Pressable, Text, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { Colors, Fonts } from '@/lib/theme';

type Props = {
  onSettings: () => void;
  onOpenCrm: () => void;
};

function GearIcon({ color }: { color: string }) {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"
        stroke={color}
        strokeWidth={1.7}
      />
      <Path
        d="M19.4 13a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V19a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H5a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1.08 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V5a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1.08 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c0 .66.38 1.26.98 1.51.2.09.42.14.64.14H19a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1.08Z"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

function CrmIcon({ color }: { color: string }) {
  return (
    <Svg width={16} height={16} viewBox="0 0 24 24" fill="none">
      <Path
        d="M14 3h7v7M10 14 21 3M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"
        stroke={color}
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function HeaderActions({ onSettings, onOpenCrm }: Props) {
  return (
    <View style={{ alignItems: 'flex-end', gap: 8 }}>
      <Pressable
        onPress={onSettings}
        accessibilityRole="button"
        accessibilityLabel="Settings"
        hitSlop={8}
        style={{
          width: 40,
          height: 40,
          borderRadius: 12,
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: Colors.white,
          borderWidth: 1,
          borderColor: Colors.border,
        }}
      >
        <GearIcon color={Colors.tealDeep} />
      </Pressable>
      <Pressable
        onPress={onOpenCrm}
        accessibilityRole="button"
        accessibilityLabel="Open CRM"
        hitSlop={6}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 6,
          paddingHorizontal: 10,
          paddingVertical: 8,
          borderRadius: 12,
          backgroundColor: Colors.tealSoft,
          borderWidth: 1,
          borderColor: '#99F6E4',
        }}
      >
        <CrmIcon color={Colors.tealDeep} />
        <Text style={{ fontFamily: Fonts.bold, fontSize: 12, color: Colors.tealDeep }}>CRM</Text>
      </Pressable>
    </View>
  );
}
