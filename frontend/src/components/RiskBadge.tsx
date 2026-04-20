interface Props {
  score: number;
  showBar?: boolean;
}

function getRiskColor(score: number) {
  if (score >= 0.7) return 'var(--red)';
  if (score >= 0.4) return 'var(--orange)';
  if (score >= 0.1) return 'var(--yellow)';
  return 'var(--green)';
}

function getRiskLabel(score: number) {
  if (score >= 0.7) return 'High Risk';
  if (score >= 0.4) return 'Medium';
  if (score >= 0.1) return 'Low';
  return 'Clean';
}

export default function RiskBadge({ score, showBar = true }: Props) {
  const color = getRiskColor(score);
  const label = getRiskLabel(score);

  return (
    <div className="risk-score">
      <span style={{ color }}>{(score * 100).toFixed(0)}%</span>
      {showBar && (
        <div className="risk-bar">
          <div
            className="risk-bar-fill"
            style={{
              width: `${score * 100}%`,
              background: color,
            }}
          />
        </div>
      )}
      <span style={{ color, fontSize: 11, fontWeight: 500 }}>{label}</span>
    </div>
  );
}
