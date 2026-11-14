function hasValue(value) {
  if (value === null || value === undefined || value === "") {
    return false;
  }

  return Number.isFinite(Number(value));
}

function ComparisonColumn({ title, meanLatency, meanCost }) {
  const hasData = hasValue(meanLatency) && hasValue(meanCost);

  return (
    <section>
      <h3>{title}</h3>
      {hasData ? (
        <>
          <p>Mean latency: {Math.round(Number(meanLatency))} ms</p>
          <p>Mean cost: {Number(meanCost).toFixed(4)} USD</p>
        </>
      ) : (
        <p>Insufficient data</p>
      )}
    </section>
  );
}

function ComparisonPanel({ metrics }) {
  return (
    <section aria-labelledby="comparison-heading">
      <h2 id="comparison-heading">Routing Comparison</h2>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: "24px",
        }}
      >
        <ComparisonColumn
          title="Adaptive Routing"
          meanLatency={metrics?.adaptive_mean_latency_ms}
          meanCost={metrics?.adaptive_mean_cost}
        />
        <ComparisonColumn
          title="Baseline Router"
          meanLatency={metrics?.baseline_mean_latency_ms}
          meanCost={metrics?.baseline_mean_cost}
        />
      </div>
    </section>
  );
}

export default ComparisonPanel;
