import React, { useEffect, useState } from "react";
import {
  indexDataset,
  streamChat,
  chatJson,
  searchProducts,
  getStatus,
} from "./api";
import "./App.css";

export default function App() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState("");
  const [jsonAnswer, setJsonAnswer] = useState(null);
  const [jsonSearch, setJsonSearch] = useState(null);
  const [activeMode, setActiveMode] = useState("stream");
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState("");

  // simple filters
  const [category, setCategory] = useState("");
  const [store, setStore] = useState("");
  const [k, setK] = useState(5);
  const [priceMin, setPriceMin] = useState("");
  const [priceMax, setPriceMax] = useState("");
  const [ratingMin, setRatingMin] = useState("");
  const [ratingMax, setRatingMax] = useState("");
  const [ratingCountMin, setRatingCountMin] = useState("");
  const [ratingCountMax, setRatingCountMax] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  async function refreshStatus() {
    try {
      setStatusError("");
      const out = await getStatus();
      setStatus(out);
    } catch (e) {
      setStatusError(String(e));
    }
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  async function handleIndex() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    try {
      const out = await indexDataset(5000);
      setAnswer(`Index result: ${JSON.stringify(out, null, 2)}`);
      await refreshStatus();
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  function buildFilter() {
    const filter = {};
    if (category.trim()) filter.main_category = category.trim();
    if (store.trim()) filter.store = store.trim();

    if (priceMin || priceMax) {
      filter.price = {
        min: priceMin ? Number(priceMin) : undefined,
        max: priceMax ? Number(priceMax) : undefined,
      };
    }
    if (ratingMin || ratingMax) {
      filter.average_rating = {
        min: ratingMin ? Number(ratingMin) : undefined,
        max: ratingMax ? Number(ratingMax) : undefined,
      };
    }
    if (ratingCountMin || ratingCountMax) {
      filter.rating_number = {
        min: ratingCountMin ? Number(ratingCountMin) : undefined,
        max: ratingCountMax ? Number(ratingCountMax) : undefined,
      };
    }
    if (dateFrom || dateTo) {
      filter.date_first_available = {
        from: dateFrom || undefined,
        to: dateTo || undefined,
      };
    }

    return Object.keys(filter).length ? filter : null;
  }

  async function handleAskStream() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    setActiveMode("stream");

    const finalFilter = buildFilter();

    try {
      await streamChat(
        { question, k: Number(k), filter: finalFilter },
        (chunk) => setAnswer((prev) => prev + chunk)
      );
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleAskJson() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    setActiveMode("json");
    const finalFilter = buildFilter();

    try {
      const out = await chatJson({
        question,
        k: Number(k),
        filter: finalFilter,
      });
      setAnswer(JSON.stringify(out, null, 2));
      setJsonAnswer(out);
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch() {
    setLoading(true);
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    setActiveMode("search");
    const finalFilter = buildFilter();

    try {
      const out = await searchProducts({
        query: question,
        k: Number(k),
        filter: finalFilter,
      });
      setSearchResults(JSON.stringify(out, null, 2));
      setJsonSearch(out);
    } catch (e) {
      setSearchResults(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="hero">
        <div>
          <div className="eyebrow">Local RAG Lab</div>
          <h1>Amazon Products RAG</h1>
          <p className="subhead">
            Local Ollama embeddings, fast retrieval, and streaming answers with
            optional Qdrant.
          </p>
          <div className="status">
            {status ? (
              <div className="status-line">
                <span>DB: {status.vector_db}</span>
                {status.collection && <span>Collection: {status.collection}</span>}
                {typeof status.count === "number" && (
                  <span>Count: {status.count}</span>
                )}
              </div>
            ) : (
              <div className="status-line muted">
                Status unavailable{statusError ? `: ${statusError}` : ""}
              </div>
            )}
          </div>
        </div>
        <div className="hero-actions">
          <button className="ghost" onClick={handleIndex} disabled={loading}>
            {loading ? "Working..." : "Index Dataset (limit 5000)"}
          </button>
          <button className="ghost" onClick={refreshStatus} disabled={loading}>
            Refresh Status
          </button>
          <div className="chip">
            {activeMode === "stream" && "Mode: Stream"}
            {activeMode === "json" && "Mode: JSON"}
            {activeMode === "search" && "Mode: Search"}
          </div>
        </div>
      </header>

      <section className="panel">
        <div className="panel-head">
          <h2>Query</h2>
          <div className="k-control">
            <label>Top K</label>
            <input
              type="number"
              min={1}
              max={20}
              value={k}
              onChange={(e) => setK(e.target.value)}
            />
          </div>
        </div>
        <div className="query-row">
          <input
            className="query-input"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder='Ask: "wireless earbuds under $50 with good ratings"'
          />
          <div className="actions">
            <button
              className="primary"
              onClick={handleAskStream}
              disabled={loading || !question.trim()}
            >
              {loading ? "Thinking..." : "Ask (Stream)"}
            </button>
            <button
              className="primary"
              onClick={handleAskJson}
              disabled={loading || !question.trim()}
            >
              {loading ? "Thinking..." : "Ask (JSON)"}
            </button>
            <button
              className="primary"
              onClick={handleSearch}
              disabled={loading || !question.trim()}
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Filters</h2>
          <div className="hint">Optional, applies to all actions</div>
        </div>
        <div className="grid">
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Main category"
          />
          <input
            value={store}
            onChange={(e) => setStore(e.target.value)}
            placeholder="Store"
          />
          <input
            value={priceMin}
            onChange={(e) => setPriceMin(e.target.value)}
            placeholder="Price min"
          />
          <input
            value={priceMax}
            onChange={(e) => setPriceMax(e.target.value)}
            placeholder="Price max"
          />
          <input
            value={ratingMin}
            onChange={(e) => setRatingMin(e.target.value)}
            placeholder="Rating min"
          />
          <input
            value={ratingMax}
            onChange={(e) => setRatingMax(e.target.value)}
            placeholder="Rating max"
          />
          <input
            value={ratingCountMin}
            onChange={(e) => setRatingCountMin(e.target.value)}
            placeholder="Rating count min"
          />
          <input
            value={ratingCountMax}
            onChange={(e) => setRatingCountMax(e.target.value)}
            placeholder="Rating count max"
          />
          <input
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            placeholder="Date from (YYYY-MM-DD)"
          />
          <input
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            placeholder="Date to (YYYY-MM-DD)"
          />
        </div>
      </section>

      <section className="results">
        <div className="result-card">
          <div className="result-head">
            <span>Answer</span>
            <button
              className="mini"
              onClick={() => {
                if (answer) navigator.clipboard.writeText(answer);
              }}
              disabled={!answer}
              title="Copy answer JSON/text"
            >
              Copy JSON
            </button>
          </div>
          <pre className="result-body">
            {answer || "Answer will stream here..."}
          </pre>
          {jsonAnswer?.recommendations?.length ? (
            <div className="cards">
              {jsonAnswer.recommendations.map((r, idx) => (
                <div className="card" key={`${r.parent_asin || idx}`}>
                  <div className="card-title">{r.title || "Untitled"}</div>
                  <div className="card-meta">
                    {r.main_category && <span>{r.main_category}</span>}
                    {r.price !== null && r.price !== undefined && (
                      <span>${r.price}</span>
                    )}
                    {r.average_rating !== null && r.average_rating !== undefined && (
                      <span>⭐ {r.average_rating}</span>
                    )}
                  </div>
                  <div className="card-meta">
                    {r.rating_number !== null && r.rating_number !== undefined && (
                      <span>{r.rating_number} ratings</span>
                    )}
                    {r.parent_asin && <span>{r.parent_asin}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
        <div className="result-card alt">
          <div className="result-head">
            <span>Search Results</span>
            <button
              className="mini"
              onClick={() => {
                if (searchResults) navigator.clipboard.writeText(searchResults);
              }}
              disabled={!searchResults}
              title="Copy search JSON/text"
            >
              Copy JSON
            </button>
          </div>
          <pre className="result-body">
            {searchResults || "Search results will appear here..."}
          </pre>
          {jsonSearch?.results?.length ? (
            <div className="cards">
              {jsonSearch.results.map((r, idx) => (
                <div className="card" key={`${r.parent_asin || idx}`}>
                  <div className="card-title">{r.title || "Untitled"}</div>
                  <div className="card-meta">
                    {r.main_category && <span>{r.main_category}</span>}
                    {r.price !== null && r.price !== undefined && (
                      <span>${r.price}</span>
                    )}
                    {r.average_rating !== null && r.average_rating !== undefined && (
                      <span>⭐ {r.average_rating}</span>
                    )}
                  </div>
                  <div className="card-meta">
                    {r.score !== null && r.score !== undefined && (
                      <span>Score: {r.score.toFixed(4)}</span>
                    )}
                    {r.parent_asin && <span>{r.parent_asin}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
