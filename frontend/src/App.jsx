import { useEffect, useState } from "react";

import ComparisonPanel from "./components/ComparisonPanel";
import ErrorBanner from "./components/ErrorBanner";
import MetricsSummary from "./components/MetricsSummary";
import PromptForm from "./components/PromptForm";
import RequestDetail from "./components/RequestDetail";
import RequestList from "./components/RequestList";
import {
  createRequest,
  getAggregateMetrics,
  getComparisonMetrics,
  getRequestDetail,
  getRequests,
} from "./services/api";

const UNKNOWN_ERROR = {
  status: "UNKNOWN",
  message: "An unexpected error occurred",
};

function normalizeError(error) {
  if (!error || typeof error !== "object") {
    return UNKNOWN_ERROR;
  }

  return {
    status: error.status ?? UNKNOWN_ERROR.status,
    message: error.message || UNKNOWN_ERROR.message,
  };
}

async function fetchDashboardData() {
  const [requestsResult, metricsResult, comparisonResult] =
    await Promise.allSettled([
      getRequests(),
      getAggregateMetrics(),
      getComparisonMetrics(),
    ]);

  return { requestsResult, metricsResult, comparisonResult };
}

function firstDashboardError(snapshot) {
  return [
    snapshot.requestsResult,
    snapshot.metricsResult,
    snapshot.comparisonResult,
  ].find((result) => result.status === "rejected")?.reason;
}

function App() {
  const [requests, setRequests] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [lastSubmission, setLastSubmission] = useState(null);
  const [error, setError] = useState(null);
  const [isPartiallyUnavailable, setIsPartiallyUnavailable] = useState(false);
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  function applyDashboardData(snapshot) {
    if (snapshot.requestsResult.status === "fulfilled") {
      setRequests(snapshot.requestsResult.value);
    }
    if (snapshot.metricsResult.status === "fulfilled") {
      setMetrics(snapshot.metricsResult.value);
    }
    if (snapshot.comparisonResult.status === "fulfilled") {
      setComparison(snapshot.comparisonResult.value);
    }

    const dashboardError = firstDashboardError(snapshot);
    setError(dashboardError ? normalizeError(dashboardError) : null);

    return snapshot.requestsResult.status === "fulfilled"
      ? snapshot.requestsResult.value
      : null;
  }

  useEffect(() => {
    let ignore = false;

    async function loadDashboard() {
      const snapshot = await fetchDashboardData();
      if (!ignore) {
        applyDashboardData(snapshot);
      }
    }

    loadDashboard();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      return undefined;
    }

    let ignore = false;

    async function loadDetail() {
      try {
        const requestDetail = await getRequestDetail(selectedId);
        if (!ignore) {
          setDetail(requestDetail);
        }
      } catch (requestError) {
        if (!ignore) {
          setError(normalizeError(requestError));
        }
      }
    }

    loadDetail();
    return () => {
      ignore = true;
    };
  }, [selectedId]);

  async function handleSubmit(prompt) {
    setIsLoading(true);
    setError(null);
    setMessage("");
    setLastSubmission(null);
    setIsPartiallyUnavailable(false);

    try {
      const { status, data } = await createRequest(prompt);

      if (status === 202) {
        setIsPartiallyUnavailable(true);
        setMessage(data.message);
      } else {
        setMessage(`Saved successfully! ID: ${data.id}`);
        setLastSubmission({ ...data, selected_model_name: null });
      }

      const requestSummaries = applyDashboardData(await fetchDashboardData());

      if (status === 200) {
        const summary = requestSummaries?.find(
          (request) => request.id === data.id,
        );
        setLastSubmission({
          ...data,
          selected_model_name: summary?.selected_model_name ?? null,
        });
      }
    } catch (requestError) {
      setError(normalizeError(requestError));
      throw requestError;
    } finally {
      setIsLoading(false);
    }
  }

  function handleSelect(id) {
    setSelectedId(id);
    setDetail(null);
    setError(null);
  }

  const evaluationUnavailable =
    lastSubmission?.status === "partial" &&
    lastSubmission.evaluation === null;

  return (
    <main style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>NeuroRoute</h1>
      <p>Adaptive inference observability dashboard.</p>

      <PromptForm onSubmit={handleSubmit} isLoading={isLoading} />
      <ErrorBanner error={error} />

      {message && <p role="status">{message}</p>}

      {isPartiallyUnavailable && (
        <p>The request is pending until routing services recover.</p>
      )}

      {lastSubmission && (
        <section aria-labelledby="latest-response-heading">
          <h2 id="latest-response-heading">Latest Response</h2>
          <p>Complexity: {lastSubmission.complexity_class}</p>
          <p>Model: {lastSubmission.selected_model_name ?? "—"}</p>
          <p>Response: {lastSubmission.execution?.response_text ?? "—"}</p>
          {evaluationUnavailable && (
            <p>
              Response generated. Quality evaluation was unavailable for this
              request.
            </p>
          )}
        </section>
      )}

      <MetricsSummary metrics={metrics} />
      <ComparisonPanel metrics={comparison} />

      <section aria-labelledby="saved-requests-heading">
        <h2 id="saved-requests-heading">Saved Requests</h2>
        <RequestList requests={requests} onSelect={handleSelect} />
      </section>

      <RequestDetail detail={detail} />
    </main>
  );
}

export default App;
