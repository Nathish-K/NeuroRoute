import { useEffect, useState } from "react";
import { createRequest, getRequests } from "./services/api";

function App() {
  const [prompt, setPrompt] = useState("");
  const [requests, setRequests] = useState([]);
  const [message, setMessage] = useState("");

  async function loadRequests() {
    try {
      const data = await getRequests();
      setRequests(data);
    } catch (error) {
      setMessage(error.message);
    }
  }

  useEffect(() => {
    loadRequests();
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();

    if (!prompt.trim()) return;

    try {
      const savedRequest = await createRequest(prompt);

      setMessage(`Saved successfully! ID: ${savedRequest.id}`);
      setPrompt("");

      await loadRequests();
    } catch (error) {
      setMessage(error.message);
    }
  }

  return (
    <div style={{ padding: "40px", fontFamily: "Arial" }}>
      <h1>NeuroRoute</h1>
      <p>Test our frontend-to-database connection.</p>

      <form onSubmit={handleSubmit}>
        <input
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Enter your prompt..."
          style={{ padding: "10px", width: "300px" }}
        />

        <button type="submit" style={{ padding: "10px" }}>
          Submit
        </button>
      </form>

      <p>{message}</p>

      <h2>Saved Requests</h2>

      {requests.map((request) => (
        <div key={request.id}>
          <p>
            #{request.id} — {request.prompt} ({request.status})
          </p>
        </div>
      ))}
    </div>
  );
}

export default App;