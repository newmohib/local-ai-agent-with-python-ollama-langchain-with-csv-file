const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:9000";

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

export async function streamRecommendations(
  { question, k = 5, filter = null },
  onEvent
) {
  const res = await fetch(`${API_BASE}/recommendations/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, k, filter }),
  });
  if (!res.ok) throw new Error("Recommendation stream failed");

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        onEvent(JSON.parse(trimmed));
      } catch {
        // ignore invalid partial lines
      }
    }
  }

  const tail = buffer.trim();
  if (tail) {
    try {
      onEvent(JSON.parse(tail));
    } catch {
      // ignore final partial line
    }
  }
}

export async function chatJson({ question, k = 5, filter = null }) {
  const res = await fetch(`${API_BASE}/recommendations`, {
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

export async function listProducts({
  limit = 50,
  offset = 0,
  parentAsin = "",
  title = "",
  store = "",
  mainCategory = "",
} = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (parentAsin) params.set("parent_asin", parentAsin);
  if (title) params.set("title", title);
  if (store) params.set("store", store);
  if (mainCategory) params.set("main_category", mainCategory);

  const res = await fetch(`${API_BASE}/products?${params.toString()}`);
  if (!res.ok) throw new Error("List products failed");
  return res.json();
}

export async function createProduct(product) {
  const res = await fetch(`${API_BASE}/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(product),
  });
  if (!res.ok) throw new Error("Create product failed");
  return res.json();
}

export async function updateProduct(parentAsin, updates) {
  const res = await fetch(`${API_BASE}/products/${parentAsin}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parent_asin: parentAsin, ...updates }),
  });
  if (!res.ok) throw new Error("Update product failed");
  return res.json();
}

export async function deleteProduct(parentAsin) {
  const res = await fetch(`${API_BASE}/products/${parentAsin}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Delete product failed");
  return res.json();
}

export async function syncProductEmbedding(parentAsin) {
  const res = await fetch(`${API_BASE}/products/${parentAsin}/sync`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Sync embedding failed");
  return res.json();
}

export async function importProducts({
  csvPath,
  limit = 500,
  keyword = null,
  skipExisting = true,
} = {}) {
  const res = await fetch(`${API_BASE}/products/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      csv_path: csvPath,
      limit,
      keyword,
      skip_existing: skipExisting,
    }),
  });
  if (!res.ok) throw new Error("Import products failed");
  return res.json();
}

export async function listUsers({ limit = 50, offset = 0, filters = {} } = {}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    ...filters,
  });
  const res = await fetch(`${API_BASE}/users?${params.toString()}`);
  if (!res.ok) throw new Error("List users failed");
  return res.json();
}

export async function searchUsers({ query, limit = 50, offset = 0 } = {}) {
  const res = await fetch(
    `${API_BASE}/users/search?query=${encodeURIComponent(query)}&limit=${encodeURIComponent(
      limit
    )}&offset=${encodeURIComponent(offset)}`
  );
  if (!res.ok) throw new Error("Search users failed");
  return res.json();
}

export async function createUser(user) {
  const res = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(user),
  });
  if (!res.ok) throw new Error("Create user failed");
  return res.json();
}

export async function updateUser(id, updates) {
  const res = await fetch(`${API_BASE}/users/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, ...updates }),
  });
  if (!res.ok) throw new Error("Update user failed");
  return res.json();
}

export async function deleteUser(id) {
  const res = await fetch(`${API_BASE}/users/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Delete user failed");
  return res.json();
}

export async function importUsers({
  csvPath = "./data/user_data.csv",
  limit = 1000,
  skipExisting = true,
} = {}) {
  const res = await fetch(`${API_BASE}/users/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      csv_path: csvPath,
      limit,
      skip_existing: skipExisting,
    }),
  });
  if (!res.ok) throw new Error("Import users failed");
  return res.json();
}

export async function syncUserEmbedding(id) {
  const res = await fetch(`${API_BASE}/users/${id}/sync`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Sync user embedding failed");
  return res.json();
}

export async function syncUsersEmbeddings({ limit = 10000 } = {}) {
  const res = await fetch(`${API_BASE}/users/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit }),
  });
  if (!res.ok) throw new Error("Sync users embeddings failed");
  return res.json();
}

export async function semanticSearchUsers({ query, k = 5 } = {}) {
  const res = await fetch(`${API_BASE}/users/search/semantic`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, k }),
  });
  if (!res.ok) throw new Error("Semantic search users failed");
  return res.json();
}
