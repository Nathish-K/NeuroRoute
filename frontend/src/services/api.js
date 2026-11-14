const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

function createApiError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function errorMessage(body, response) {
  if (typeof body?.detail === "string" && body.detail.trim()) {
    return body.detail;
  }

  if (Array.isArray(body?.detail)) {
    const messages = body.detail
      .map((entry) => entry?.msg)
      .filter((message) => typeof message === "string" && message.trim());

    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  return response.statusText || `Request failed with HTTP ${response.status}`;
}

async function request(path, options) {
  let response;

  try {
    response = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw createApiError("NETWORK", "Unable to reach the NeuroRoute API");
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    if (response.ok) {
      throw createApiError(
        response.status,
        "The NeuroRoute API returned an invalid response",
      );
    }
  }

  if (!response.ok) {
    throw createApiError(response.status, errorMessage(body, response));
  }

  return { status: response.status, data: body };
}

export async function createRequest(prompt) {
  return request("/api/requests/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ prompt }),
  });
}

export async function getRequests() {
  const { data } = await request("/api/requests/");
  return data;
}

export async function getRequestDetail(id) {
  const { data } = await request(`/api/requests/${encodeURIComponent(id)}`);
  return data;
}

export async function submitFeedback(requestId, rating, comment) {
  const payload = { rating };
  if (comment !== undefined) {
    payload.comment = comment;
  }

  const { data } = await request(
    `/api/requests/${encodeURIComponent(requestId)}/feedback`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  return data;
}

export async function getFeedback(requestId) {
  const { data } = await request(
    `/api/requests/${encodeURIComponent(requestId)}/feedback`,
  );
  return data;
}

export async function getAggregateMetrics() {
  const { data } = await request("/api/requests/metrics");
  return data;
}

export async function getComparisonMetrics() {
  const { data } = await request("/api/requests/metrics");
  return data;
}

export async function getFeedbackSummary() {
  const { data } = await request("/api/metrics/feedback-summary");
  return data;
}
