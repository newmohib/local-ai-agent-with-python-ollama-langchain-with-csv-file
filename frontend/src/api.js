const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9000";

export async function getStatus() {
  const res = await fetch(`${API_BASE}/status`);
  if (!res.ok) throw new Error("Status failed");
  return res.json();
}

export async function indexDataset(limit = 5000) {
  const res = await fetch(`${API_BASE}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit }),
  });
  if (!res.ok) throw new Error("Index failed");
  return res.json();
}

export async function streamChat({ question, k = 5, filter = null }, onChunk) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k, filter }),
  });
  if (!res.ok) throw new Error("Chat failed");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    onChunk(text);
  }
}

export async function chatJson({ question, k = 5, filter = null }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k, filter }),
  });
  if (!res.ok) throw new Error("Chat failed");
  return res.json();
}

export async function searchProducts({ query, k = 5, filter = null }) {
  const res = await fetch(`${API_BASE}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, k, filter }),
  });
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}
