import type { ReactNode } from "react";

export interface KpiCardProps {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
}

export default function KpiCard({ label, value, unit, hint }: KpiCardProps) {
  return (
    <div className="kpi-card">
      <span className="kpi-label">{label}</span>
      <div className="kpi-value">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}
