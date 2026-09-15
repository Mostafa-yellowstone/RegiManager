import Svg, { Circle, Path, Polyline } from 'react-native-svg';

type Props = {
  color: string;
  values?: number[];
  width?: number;
  height?: number;
};

export function Sparkline({ color, values, width = 56, height = 28 }: Props) {
  const pts =
    values && values.length > 1
      ? values
      : [12, 18, 14, 22, 17, 26, 24];
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = Math.max(1, max - min);
  const coords = pts
    .map((v, i) => {
      const x = (i / (pts.length - 1)) * (width - 4) + 2;
      const y = height - 4 - ((v - min) / span) * (height - 8);
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <Svg width={width} height={height}>
      <Polyline
        points={coords}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.9}
      />
      {coords.split(' ').slice(-1).map((pair) => {
        const [x, y] = pair.split(',').map(Number);
        return <Circle key={`${x}-${y}`} cx={x} cy={y} r={2.5} fill={color} />;
      })}
      <Path d="" />
    </Svg>
  );
}
