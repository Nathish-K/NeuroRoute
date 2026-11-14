function formatNumber(value, fractionDigits) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const numericValue = Number(value);

  return Number.isFinite(numericValue) ? numericValue.toFixed(fractionDigits) : "—";
}

function truncatePrompt(prompt) {
  return prompt.length > 100 ? `${prompt.slice(0, 100)}…` : prompt;
}

function RequestListItem({ request, onSelect }) {
  const {
    id,
    prompt,
    status,
    complexity_class,
    selected_model_name,
    routing_policy,
    latency_ms,
    estimated_cost,
    quality_score,
  } = request;

  return (
    <li>
      <button type="button" onClick={() => onSelect(id)}>
        <p>{truncatePrompt(prompt)}</p>
        <p>Status: {status}</p>
        <p>Complexity: {complexity_class ?? "—"}</p>
        <p>Model: {selected_model_name ?? "—"}</p>
        <p>Routing policy: {routing_policy ?? "—"}</p>
        <p>Latency: {latency_ms ?? "—"} ms</p>
        <p>Estimated cost: {formatNumber(estimated_cost, 4)} USD</p>
        <p>Quality score: {formatNumber(quality_score, 2)}</p>
      </button>
    </li>
  );
}

export default RequestListItem;
