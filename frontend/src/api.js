const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9000";

export async function getStatus() {
  const res = await fetch(`${API_BASE}/status`);
  if (!res.ok) throw new Error("Status failed");
  return res.json();
}

export async function exportDataset({
  limit = 500,
  keyword = "earbuds",
  outputPath = "./data/amazon_products.csv",
} = {}) {
  const res = await fetch(`${API_BASE}/dataset/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit, keyword, output_path: outputPath }),
  });
  if (!res.ok) throw new Error("Dataset export failed");
  return res.json();
}

export async function indexDataset({
  limit = 500,
  keyword = "earbuds",
  dataSource = "csv",
  csvPath = "./data/amazon_products.csv",
} = {}) {
  const res = await fetch(`${API_BASE}/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      limit,
      keyword,
      data_source: dataSource,
      csv_path: csvPath,
      batch_size: 10,
      reset: true,
    }),
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
