function ErrorBanner({ error }) {
  if (!error) {
    return null;
  }

  return (
    <div role="alert">
      <strong>Error {error.status}:</strong> {error.message}
    </div>
  );
}

export default ErrorBanner;
