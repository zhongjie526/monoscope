interface Props {
  severity: string;
}

export default function SeverityBadge({ severity }: Props) {
  const cls =
    severity === 'critical'
      ? 'badge-critical'
      : severity === 'high'
      ? 'badge-high'
      : severity === 'medium'
      ? 'badge-medium'
      : 'badge-low';

  return <span className={`badge ${cls}`}>{severity}</span>;
}
