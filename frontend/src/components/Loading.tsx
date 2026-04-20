export default function Loading({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="loading">
      <div className="spinner" />
      <span>{message}</span>
    </div>
  );
}
