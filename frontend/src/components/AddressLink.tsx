import { useNavigate } from 'react-router-dom';

interface Props {
  address: string;
  truncate?: boolean;
}

export default function AddressLink({ address, truncate = true }: Props) {
  const navigate = useNavigate();
  const display = truncate
    ? `${address.slice(0, 6)}…${address.slice(-4)}`
    : address;

  return (
    <span
      className="address"
      title={address}
      onClick={() => navigate(`/wallet/${address}`)}
    >
      {display}
    </span>
  );
}
