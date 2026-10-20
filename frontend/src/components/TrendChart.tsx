interface Point {
  label: string;
  value: number;
}

export interface TrendChartProps {
  data: Point[];
  mode: "line" | "bars";
  color?: string;
  height?: number;
}

/** 纯 SVG 图表：不引图表库，够画趋势与分布即可。 */
export default function TrendChart({ data, mode, color = "#0d8f6f", height = 120 }: TrendChartProps) {
  const width = 360;
  const pad = 8;
  const max = Math.max(...data.map((point) => point.value), 1);
  const step = data.length > 1 ? (width - pad * 2) / (data.length - 1) : 0;

  if (mode === "bars") {
    const gap = 10;
    const barWidth = Math.max(8, (width - pad * 2 - gap * (data.length - 1)) / Math.max(data.length, 1));
    return (
      <div className="chart-block">
        <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" role="img" aria-label="分布">
          {data.map((point, index) => {
            const barHeight = Math.max(3, (point.value / max) * (height - 24));
            const x = pad + index * (barWidth + gap);
            return (
              <rect
                key={point.label}
                x={x}
                y={height - 18 - barHeight}
                width={barWidth}
                height={barHeight}
                rx={4}
                fill={point.value === max ? color : "rgba(13,143,111,.28)"}
              />
            );
          })}
        </svg>
        <div className="chart-labels" style={{ gridTemplateColumns: `repeat(${data.length}, 1fr)` }}>
          {data.map((point) => (
            <span key={point.label}>{point.label}</span>
          ))}
        </div>
      </div>
    );
  }

  const points = data
    .map((point, index) => {
      const x = pad + index * step;
      const y = height - 18 - (point.value / max) * (height - 30);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="chart-block">
      <svg viewBox={`0 0 ${width} ${height}`} className="chart-svg" role="img" aria-label="趋势">
        <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {data.map((point, index) => (
          <circle
            key={point.label}
            cx={pad + index * step}
            cy={height - 18 - (point.value / max) * (height - 30)}
            r={2.6}
            fill={color}
          />
        ))}
      </svg>
      <div className="chart-labels" style={{ gridTemplateColumns: `repeat(${data.length}, 1fr)` }}>
        {data.map((point) => (
          <span key={point.label}>{point.label}</span>
        ))}
      </div>
    </div>
  );
}
