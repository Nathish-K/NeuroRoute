function finiteNumber(value, fallback = 0) {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }

  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function MetricsSummary({ metrics }) {
  const totalCount = finiteNumber(metrics?.total_count);
  const hasData = totalCount > 0;
  const meanLatency = hasData
    ? finiteNumber(metrics?.mean_latency_ms)
    : 0;
  const meanCost = hasData
    ? finiteNumber(metrics?.mean_estimated_cost)
    : 0;
  const meanQuality = hasData
    ? finiteNumber(metrics?.mean_quality_score)
    : 0;

  return (
    <section aria-labelledby="metrics-summary-heading">
      <h2 id="metrics-summary-heading">Metrics Summary</h2>
      <p>Total requests: {Math.round(totalCount)}</p>
      <p>Mean latency: {Math.round(meanLatency)} ms</p>
      <p>Mean estimated cost: {meanCost.toFixed(4)} USD</p>
      <p>Mean quality score: {meanQuality.toFixed(2)}</p>
    </section>
  );
}

export default MetricsSummary;
