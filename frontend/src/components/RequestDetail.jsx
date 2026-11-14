function formatNumber(value, fractionDigits, suffix = "") {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const numericValue = Number(value);

  return Number.isFinite(numericValue)
    ? `${numericValue.toFixed(fractionDigits)}${suffix}`
    : "—";
}

function RequestDetail({ detail }) {
  if (!detail) {
    return null;
  }

  const { execution, evaluation, feedback, routing_decision } = detail;

  return (
    <section aria-labelledby="request-detail-heading">
      <h2 id="request-detail-heading">Request Details</h2>
      <p>Prompt: {detail.prompt}</p>
      <p>Status: {detail.status}</p>
      <p>Complexity: {detail.complexity_class ?? "—"}</p>
      <p>End-to-end latency: {detail.end_to_end_latency_ms ?? "—"} ms</p>

      <h3>Routing</h3>
      <p>Explanation: {routing_decision?.explanation ?? "—"}</p>

      <h3>Execution</h3>
      <p>Response: {execution?.response_text ?? "—"}</p>
      <p>Input tokens: {execution?.input_token_count ?? "—"}</p>
      <p>Output tokens: {execution?.output_token_count ?? "—"}</p>
      <p>Latency: {execution?.latency_ms ?? "—"} ms</p>
      <p>
        Estimated cost: {formatNumber(execution?.estimated_cost, 4, " USD")}
      </p>

      <h3>Evaluation</h3>
      <p>Quality score: {formatNumber(evaluation?.quality_score, 2)}</p>
      <p>Confidence: {formatNumber(evaluation?.confidence, 2)}</p>

      {feedback && <p>Feedback rating: {feedback.rating}</p>}
    </section>
  );
}

export default RequestDetail;
