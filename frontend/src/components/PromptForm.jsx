import { useState } from "react";

function PromptForm({ onSubmit, isLoading = false }) {
  const [prompt, setPrompt] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();

    if (!prompt.trim() || isLoading) {
      return;
    }

    try {
      await onSubmit(prompt);
      setPrompt("");
    } catch {
      // The parent owns API error feedback. Keep the prompt so it can be
      // corrected or resubmitted after the error is shown.
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Submit a prompt">
      <input
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        placeholder="Enter your prompt..."
        style={{ padding: "10px", width: "300px" }}
        disabled={isLoading}
      />

      <button type="submit" style={{ padding: "10px" }} disabled={isLoading}>
        {isLoading ? "Submitting..." : "Submit"}
      </button>
    </form>
  );
}

export default PromptForm;
