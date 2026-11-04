const API_URL = "http://localhost:8000";

export async function createRequest(prompt) {
  const response = await fetch(`${API_URL}/api/requests/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ prompt }),
  });

  if (!response.ok) {
    throw new Error("Failed to create request");
  }

  return await response.json();
}

export async function getRequests() {
  const response = await fetch(`${API_URL}/api/requests/`);

  if (!response.ok) {
    throw new Error("Failed to fetch requests");
  }

  return await response.json();
}