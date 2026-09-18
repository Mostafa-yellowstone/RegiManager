import { Children, type ReactNode } from 'react';
import { View } from 'react-native';

type Props = {
  children: ReactNode;
  gap?: number;
};

/** Strict 2-column metric layout — avoids flex-wrap overlap bugs. */
export function MetricGrid({ children, gap = 12 }: Props) {
  const items = Children.toArray(children).filter(Boolean);
  const rows: ReactNode[][] = [];

  for (let i = 0; i < items.length; i += 2) {
    rows.push(items.slice(i, i + 2));
  }

  return (
    <View style={{ gap }}>
      {rows.map((row, rowIndex) => (
        <View key={`metric-row-${rowIndex}`} style={{ flexDirection: 'row', gap }}>
          {row.map((child, colIndex) => (
            <View key={`metric-cell-${rowIndex}-${colIndex}`} style={{ flex: 1, minWidth: 0 }}>
              {child}
            </View>
          ))}
          {row.length === 1 ? <View style={{ flex: 1 }} /> : null}
        </View>
      ))}
    </View>
  );
}
