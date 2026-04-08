import React, { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  exportDataset,
  indexDataset,
  streamChat,
  streamRecommendations,
  chatJson,
  searchProducts,
  getStatus,
  listProducts,
  createProduct,
  updateProduct,
  deleteProduct,
  syncProductEmbedding,
  importProducts,
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  importUsers,
  syncUserEmbedding,
  syncUsersEmbeddings,
  semanticSearchUsers,
} from "./api";
import "./App.css";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState("");
  const [jsonAnswer, setJsonAnswer] = useState(null);
  const [jsonSearch, setJsonSearch] = useState(null);
  const [activeMode, setActiveMode] = useState("stream");
  const [lastFilter, setLastFilter] = useState(null);
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [indexKeyword, setIndexKeyword] = useState("earbuds");
  const [indexLimit, setIndexLimit] = useState(500);
  const [csvPath, setCsvPath] = useState("./data/amazon_products.csv");
  const [products, setProducts] = useState([]);
  const [productError, setProductError] = useState("");
  const [importing, setImporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [expandedRows, setExpandedRows] = useState(() => new Set());
  const [appTableCollapsed, setAppTableCollapsed] = useState(false);
  const [resultsCollapsed, setResultsCollapsed] = useState(false);
  const [expandedAnswerCards, setExpandedAnswerCards] = useState(() => new Set());
  const [expandedSearchCards, setExpandedSearchCards] = useState(() => new Set());
  const [users, setUsers] = useState([]);
  const [userError, setUserError] = useState("");
  const [userSemanticQuery, setUserSemanticQuery] = useState("");
  const [userSemanticResults, setUserSemanticResults] = useState([]);
  const [userSemanticActive, setUserSemanticActive] = useState(false);
  const [userForm, setUserForm] = useState({
    id: "",
    first_name: "",
    last_name: "",
    full_name: "",
    city: "",
    mobile: "",
    dob: "",
    gender: "",
    policynum: "",
    clntid: "",
  });
  const [userImporting, setUserImporting] = useState(false);
  const [userExpanded, setUserExpanded] = useState(() => new Set());
  const [userSyncing, setUserSyncing] = useState({});
  const [usersBulkSyncing, setUsersBulkSyncing] = useState(false);

  const showProducts = location.pathname.startsWith("/products") || location.pathname === "/";
  const showUsers = location.pathname.startsWith("/users");
  const [rowSyncing, setRowSyncing] = useState({});
  const [appSearch, setAppSearch] = useState({
    parent_asin: "",
    title: "",
    store: "",
    main_category: "",
  });
  const [productForm, setProductForm] = useState({
    parent_asin: "",
    title: "",
    price: "",
    average_rating: "",
    rating_number: "",
    main_category: "",
    store: "",
  });
  const userExtraCols = userSemanticActive
    ? getUserExtraColumns(userSemanticQuery)
    : [];
  const userGridTemplate = [
    "1.2fr",
    "2fr",
    "0.9fr",
    "0.9fr",
    ...userExtraCols.map(() => "0.7fr"),
    "1fr",
  ].join(" ");

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

  function getUserExtraColumns(query) {
    const q = (query || "").toLowerCase();
    if (!q) return [];
    const candidates = [
      { keys: ["age"], key: "age", label: "Age" },
      { keys: ["dob", "birth"], key: "dob", label: "DOB" },
      { keys: ["gender"], key: "gender", label: "Gender" },
      { keys: ["policy", "policynum"], key: "policynum", label: "Policy" },
      { keys: ["client", "clntid"], key: "clntid", label: "Client ID" },
      { keys: ["nid"], key: "nid", label: "NID" },
      { keys: ["father"], key: "father_name", label: "Father Name" },
      { keys: ["issue"], key: "issue_date", label: "Issue Date" },
      { keys: ["address", "addr"], key: "addr1", label: "Address" },
      { keys: ["first"], key: "first_name", label: "First Name" },
      { keys: ["last"], key: "last_name", label: "Last Name" },
      { keys: ["full", "name"], key: "full_name", label: "Full Name" },
      { keys: ["city"], key: "city", label: "City" },
      { keys: ["mobile", "phone"], key: "mobile", label: "Mobile" },
      { keys: ["remarks"], key: "remarks", label: "Remarks" },
    ];
    const picked = [];
    const baseCols = new Set(["full_name", "city", "mobile"]);
    for (const item of candidates) {
      if (picked.length >= 2) break;
      if (item.keys.some((k) => q.includes(k))) {
        if (baseCols.has(item.key)) {
          continue;
        }
        if (!picked.find((p) => p.key === item.key)) {
          picked.push(item);
        }
      }
    }
    return picked.slice(0, 2);
  }

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
    refreshProducts();
    refreshUsers();
  }, []);

  useEffect(() => {
    if (location.pathname === "/") {
      navigate("/products", { replace: true });
    }
  }, [location.pathname, navigate]);

  async function handleIndex() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    try {
      const out = await indexDataset({
        limit: Number(indexLimit),
        keyword: indexKeyword.trim() || null,
        dataSource: "csv",
        csvPath,
      });
      setAnswer(`Index result: ${JSON.stringify(out, null, 2)}`);
      await refreshStatus();
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleExportCsv() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer(null);
    setJsonSearch(null);
    try {
      const out = await exportDataset({
        limit: Number(indexLimit),
        keyword: indexKeyword.trim() || null,
        outputPath: csvPath,
      });
      setAnswer(`CSV export result: ${JSON.stringify(out, null, 2)}`);
    } catch (e) {
      setAnswer(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function refreshProducts(params = {}) {
    try {
      setProductError("");
      const out = await listProducts({
        limit: 50,
        offset: 0,
        parentAsin: params.parent_asin || appSearch.parent_asin,
        title: params.title || appSearch.title,
        store: params.store || appSearch.store,
        mainCategory: params.main_category || appSearch.main_category,
      });
      setProducts(out.products || []);
    } catch (e) {
      setProductError(String(e));
    }
  }

  async function refreshUsers() {
    try {
      setUserError("");
      const out = await listUsers({
        limit: 10,
        offset: 0,
        filters: {},
      });
      setUsers(out.users || []);
    } catch (e) {
      setUserError(String(e));
    }
  }

  async function handleCreateProduct() {
    try {
      setProductError("");
      const payload = {
        parent_asin: productForm.parent_asin.trim(),
        title: productForm.title.trim() || null,
        price: productForm.price ? Number(productForm.price) : null,
        average_rating: productForm.average_rating
          ? Number(productForm.average_rating)
          : null,
        rating_number: productForm.rating_number
          ? Number(productForm.rating_number)
          : null,
        main_category: productForm.main_category.trim() || null,
        store: productForm.store.trim() || null,
      };
      if (!payload.parent_asin) {
        setProductError("parent_asin is required");
        return;
      }
      await createProduct(payload);
      setProductForm({
        parent_asin: "",
        title: "",
        price: "",
        average_rating: "",
        rating_number: "",
        main_category: "",
        store: "",
      });
      await refreshProducts();
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    }
  }

  async function handleImportToAppDb() {
    try {
      setImporting(true);
      setProductError("");
      const out = await importProducts({
        csvPath,
        limit: Number(indexLimit),
        keyword: indexKeyword.trim() || null,
        skipExisting: true,
      });
      setAnswer(`Import result: ${JSON.stringify(out, null, 2)}`);
      await refreshProducts();
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    } finally {
      setImporting(false);
    }
  }

  async function handleSyncEmbeddings() {
    try {
      setSyncing(true);
      setProductError("");
      const out = await indexDataset({
        limit: Number(indexLimit),
        keyword: indexKeyword.trim() || null,
        dataSource: "app_db",
        csvPath,
      });
      setAnswer(`Sync result: ${JSON.stringify(out, null, 2)}`);
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    } finally {
      setSyncing(false);
    }
  }

  async function handleUpdateProduct(parentAsin, field, value) {
    try {
      setProductError("");
      const updates = { [field]: value };
      await updateProduct(parentAsin, updates);
      await refreshProducts();
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    }
  }

  async function handleSyncProduct(parentAsin) {
    try {
      setProductError("");
      setRowSyncing((prev) => ({ ...prev, [parentAsin]: true }));
      await syncProductEmbedding(parentAsin);
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    } finally {
      setRowSyncing((prev) => ({ ...prev, [parentAsin]: false }));
    }
  }

  async function handleDeleteProduct(parentAsin) {
    try {
      setProductError("");
      await deleteProduct(parentAsin);
      await refreshProducts();
      await refreshStatus();
    } catch (e) {
      setProductError(String(e));
    }
  }

  function toggleUserRow(id) {
    setUserExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleAppSearch() {
    await refreshProducts();
  }

  async function handleAppSearchClear() {
    setAppSearch({ parent_asin: "", title: "", store: "", main_category: "" });
    await refreshProducts({
      parent_asin: "",
      title: "",
      store: "",
      main_category: "",
    });
  }

  async function handleUserSemanticSearch() {
    try {
      setUserError("");
      if (!userSemanticQuery.trim()) {
        setUserSemanticResults([]);
        setUserSemanticActive(false);
        return;
      }
      const out = await semanticSearchUsers({
        query: userSemanticQuery.trim(),
        k: 5,
      });
      setUserSemanticResults(out.results || []);
      setUserSemanticActive(true);
    } catch (e) {
      setUserError(String(e));
    }
  }

  function handleUserSemanticReset() {
    setUserSemanticQuery("");
    setUserSemanticResults([]);
    setUserSemanticActive(false);
  }

  async function handleUserCreate() {
    try {
      setUserError("");
      if (!userForm.id) {
        setUserError("id is required");
        return;
      }
      await createUser(userForm);
      await refreshUsers();
    } catch (e) {
      setUserError(String(e));
    }
  }

  async function handleUserDelete(id) {
    try {
      setUserError("");
      await deleteUser(id);
      await refreshUsers();
    } catch (e) {
      setUserError(String(e));
    }
  }

  async function handleUserImport() {
    try {
      setUserImporting(true);
      setUserError("");
      await importUsers({ csvPath: "./data/user_data.csv", limit: 1000 });
      await refreshUsers();
    } catch (e) {
      setUserError(String(e));
    } finally {
      setUserImporting(false);
    }
  }

  async function handleUserSync(id) {
    try {
      setUserError("");
      setUserSyncing((prev) => ({ ...prev, [id]: true }));
      await syncUserEmbedding(id);
    } catch (e) {
      setUserError(String(e));
    } finally {
      setUserSyncing((prev) => ({ ...prev, [id]: false }));
    }
  }

  async function handleUsersBulkSync() {
    try {
      setUsersBulkSyncing(true);
      setUserError("");
      await syncUsersEmbeddings({ limit: 10000 });
    } catch (e) {
      setUserError(String(e));
    } finally {
      setUsersBulkSyncing(false);
    }
  }

  function toggleRow(parentAsin) {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(parentAsin)) next.delete(parentAsin);
      else next.add(parentAsin);
      return next;
    });
  }

  function toggleAnswerCard(key) {
    setExpandedAnswerCards((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSearchCard(key) {
    setExpandedSearchCards((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
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
    setLastFilter(finalFilter);

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

  async function handleAskFastStream() {
    setLoading(true);
    setAnswer("");
    setSearchResults("");
    setJsonAnswer({ recommendations: [] });
    setJsonSearch(null);
    setActiveMode("fast-stream");

    const finalFilter = buildFilter();
    setLastFilter(finalFilter);

    try {
      await streamRecommendations(
        { question, k: Number(k), filter: finalFilter },
        (evt) => {
          setAnswer((prev) => prev + `${JSON.stringify(evt)}\n`);
          if (evt.event === "item" && evt.recommendation) {
            setJsonAnswer((prev) => ({
              ...prev,
              recommendations: [
                ...(prev?.recommendations || []),
                evt.recommendation,
              ],
            }));
          }
        }
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
    setLastFilter(finalFilter);

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
    setLastFilter(finalFilter);

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
          <div className="tabs">
            <NavLink
              to="/products"
              className={({ isActive }) => `tab ${isActive ? "active" : ""}`}
            >
              Products
            </NavLink>
            <NavLink
              to="/users"
              className={({ isActive }) => `tab ${isActive ? "active" : ""}`}
            >
              Users
            </NavLink>
          </div>
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
          <button className="ghost" onClick={refreshStatus} disabled={loading}>
            Refresh Status
          </button>
          <div className="chip">
            {activeMode === "stream" && "Mode: Stream"}
            {activeMode === "fast-stream" && "Mode: Fast Stream"}
            {activeMode === "json" && "Mode: JSON"}
            {activeMode === "search" && "Mode: Search"}
          </div>
        </div>
      </header>

      {showProducts && (
<section className="panel">
        <div className="panel-head">
          <h2>Local CSV</h2>
          <div className="hint">Export from HuggingFace once, then index from CSV</div>
        </div>
        <div className="grid">
          <input
            value={indexKeyword}
            onChange={(e) => setIndexKeyword(e.target.value)}
            placeholder="Dataset keyword"
          />
          <input
            type="number"
            min={1}
            value={indexLimit}
            onChange={(e) => setIndexLimit(e.target.value)}
            placeholder="Limit"
          />
          <input
            value={csvPath}
            onChange={(e) => setCsvPath(e.target.value)}
            placeholder="CSV path"
          />
        </div>
        <div className="actions space-top">
          <button className="ghost" onClick={handleExportCsv} disabled={loading}>
            {loading ? "Working..." : "Export CSV"}
          </button>
          <button className="ghost" onClick={handleIndex} disabled={loading}>
            {loading ? "Working..." : "Index CSV"}
          </button>
        </div>
      </section>

)}

      {showProducts && (
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
              onClick={handleAskFastStream}
              disabled={loading || !question.trim()}
            >
              {loading ? "Streaming..." : "Fast Stream"}
            </button>
            <button
              className="primary"
              onClick={handleAskJson}
              disabled={loading || !question.trim()}
            >
              {loading ? "Searching..." : "Fast JSON"}
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

)}

      {showProducts && (
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

)}

      {showProducts && (
<section className="results-section">
        <div className="results-head">
          <div className="results-title">Results</div>
          <button
            className="ghost"
            onClick={() => setResultsCollapsed((prev) => !prev)}
          >
            {resultsCollapsed ? "Expand Results ▸" : "Collapse Results ▾"}
          </button>
        </div>
        <div className="results">
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
            {!resultsCollapsed && (
              <>
                {lastFilter && (
                  <div className="filter-summary">
                    Filter: {JSON.stringify(lastFilter)}
                  </div>
                )}
                <pre className="result-body">
                  {answer || "Answer will stream here..."}
                </pre>
                {jsonAnswer?.recommendations?.length ? (
                  <div className="cards">
                    {jsonAnswer.recommendations.map((r, idx) => {
                      const cardKey = String(r.parent_asin || idx);
                      return (
                        <div className="card" key={cardKey}>
                          <div className="card-title">{r.title || "Untitled"}</div>
                          <div className="card-meta">
                            {r.main_category && <span>{r.main_category}</span>}
                            {r.price !== null && r.price !== undefined && (
                              <span>${r.price}</span>
                            )}
                            {r.average_rating !== null &&
                              r.average_rating !== undefined && (
                                <span>⭐ {r.average_rating}</span>
                              )}
                          </div>
                          <div className="card-meta">
                            {r.rating_number !== null &&
                              r.rating_number !== undefined && (
                                <span>{r.rating_number} ratings</span>
                              )}
                            {r.parent_asin && <span>{r.parent_asin}</span>}
                          </div>
                          <div className="card-actions">
                            <button
                              className="ghost"
                              onClick={() => toggleAnswerCard(cardKey)}
                            >
                              {expandedAnswerCards.has(cardKey)
                                ? "Hide Details"
                                : "Details"}
                            </button>
                          </div>
                          {expandedAnswerCards.has(cardKey) && (
                            <div className="card-detail">
                              <div>Store: {r.store ?? "-"}</div>
                              <div>Date: {r.date_first_available ?? "-"}</div>
                              <div>Image: {r.image ? "Yes" : "No"}</div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </>
            )}
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
            {!resultsCollapsed && (
              <>
                <pre className="result-body">
                  {searchResults || "Search results will appear here..."}
                </pre>
                {jsonSearch?.results?.length ? (
                  <div className="cards">
                    {jsonSearch.results.map((r, idx) => {
                      const cardKey = String(r.parent_asin || idx);
                      return (
                        <div className="card" key={cardKey}>
                          <div className="card-title">{r.title || "Untitled"}</div>
                          <div className="card-meta">
                            {r.main_category && <span>{r.main_category}</span>}
                            {r.price !== null && r.price !== undefined && (
                              <span>${r.price}</span>
                            )}
                            {r.average_rating !== null &&
                              r.average_rating !== undefined && (
                                <span>⭐ {r.average_rating}</span>
                              )}
                          </div>
                          <div className="card-meta">
                            {r.score !== null && r.score !== undefined && (
                              <span>Score: {r.score.toFixed(4)}</span>
                            )}
                            {r.parent_asin && <span>{r.parent_asin}</span>}
                          </div>
                          <div className="card-actions">
                            <button
                              className="ghost"
                              onClick={() => toggleSearchCard(cardKey)}
                            >
                              {expandedSearchCards.has(cardKey)
                                ? "Hide Details"
                                : "Details"}
                            </button>
                          </div>
                          {expandedSearchCards.has(cardKey) && (
                            <div className="card-detail">
                              <div>Store: {r.store ?? "-"}</div>
                              <div>Date: {r.date_first_available ?? "-"}</div>
                              <div>Image: {r.image ? "Yes" : "No"}</div>
                              <div>Snippet: {r.snippet ?? "-"}</div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </section>

)}

      {showProducts && (
<section className="panel">
        <div className="panel-head">
          <h2>App DB</h2>
          <div className="actions">
            <button
              className="ghost"
              onClick={() => setAppTableCollapsed((prev) => !prev)}
            >
              {appTableCollapsed ? "Expand Table ▸" : "Collapse Table ▾"}
            </button>
          </div>
        </div>
        <div className="hint">
          Manage SQLite records. Insert/update/delete auto-sync embeddings.
        </div>
        <div className="grid space-top">
          <input
            value={appSearch.parent_asin}
            onChange={(e) =>
              setAppSearch((s) => ({ ...s, parent_asin: e.target.value }))
            }
            placeholder="Search parent_asin"
          />
          <input
            value={appSearch.title}
            onChange={(e) => setAppSearch((s) => ({ ...s, title: e.target.value }))}
            placeholder="Search title"
          />
          <input
            value={appSearch.store}
            onChange={(e) => setAppSearch((s) => ({ ...s, store: e.target.value }))}
            placeholder="Search store"
          />
          <input
            value={appSearch.main_category}
            onChange={(e) =>
              setAppSearch((s) => ({ ...s, main_category: e.target.value }))
            }
            placeholder="Search category"
          />
        </div>
        <div className="actions space-top">
          <button className="ghost" onClick={handleAppSearch}>
            Search
          </button>
          <button className="ghost" onClick={handleAppSearchClear}>
            Clear
          </button>
        </div>
        <div className="grid space-top">
          <input
            value={productForm.parent_asin}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, parent_asin: e.target.value }))
            }
            placeholder="parent_asin"
          />
          <input
            value={productForm.title}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, title: e.target.value }))
            }
            placeholder="Title"
          />
          <input
            value={productForm.price}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, price: e.target.value }))
            }
            placeholder="Price"
          />
          <input
            value={productForm.average_rating}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, average_rating: e.target.value }))
            }
            placeholder="Avg rating"
          />
          <input
            value={productForm.rating_number}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, rating_number: e.target.value }))
            }
            placeholder="Rating count"
          />
          <input
            value={productForm.main_category}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, main_category: e.target.value }))
            }
            placeholder="Main category"
          />
          <input
            value={productForm.store}
            onChange={(e) =>
              setProductForm((p) => ({ ...p, store: e.target.value }))
            }
            placeholder="Store"
          />
        </div>
        <div className="actions space-top">
          <button className="primary" onClick={handleCreateProduct}>
            Add / Update
          </button>
          <button className="ghost" onClick={handleImportToAppDb} disabled={importing}>
            Import CSV (Skip Existing)
            {importing && <span className="spinner" />}
          </button>
          <button className="ghost" onClick={handleSyncEmbeddings} disabled={syncing}>
            Sync Embeddings
            {syncing && <span className="spinner" />}
          </button>
          {productError && <span className="hint">{productError}</span>}
        </div>

        {!appTableCollapsed && (
          <div className="table space-top">
            <div className="table-row header">
              <div>ASIN</div>
              <div>Title</div>
              <div>Price</div>
              <div>Rating</div>
              <div>Actions</div>
            </div>
            {products.length === 0 ? (
              <div className="table-row empty">No products yet.</div>
            ) : (
              products.map((p, idx) => {
                const rowKey = String(p.parent_asin ?? idx);
                return (
                <div key={rowKey}>
                  <div className="table-row">
                    <div className="mono">{p.parent_asin ?? "-"}</div>
                    <div title={p.title || ""}>{p.title || "Untitled"}</div>
                    <div>${p.price ?? "-"}</div>
                    <div>{p.average_rating ?? "-"}</div>
                    <div className="actions">
                    <button
                      className="ghost icon-button"
                      onClick={() => toggleRow(rowKey)}
                      title="Details"
                    >
                      {expandedRows.has(rowKey) ? "▾" : "▸"}
                    </button>
                    <button
                      className="ghost icon-button"
                      onClick={() => handleSyncProduct(p.parent_asin)}
                      title="Sync"
                      disabled={!!rowSyncing[p.parent_asin]}
                    >
                      {rowSyncing[p.parent_asin] ? (
                        <span className="spinner small" />
                      ) : (
                        "⟳"
                      )}
                    </button>
                    <button
                      className="ghost icon-button danger"
                      onClick={() => handleDeleteProduct(p.parent_asin)}
                      title="Delete"
                    >
                      ✕
                    </button>
                    </div>
                  </div>
                  {expandedRows.has(rowKey) && (
                    <div className="table-row detail">
                      <div className="mono">Details</div>
                      <div className="detail-grid">
                        <div>Category: {p.main_category ?? "-"}</div>
                        <div>Store: {p.store ?? "-"}</div>
                        <div>Rating Count: {p.rating_number ?? "-"}</div>
                        <div>Date: {p.date_first_available ?? "-"}</div>
                        <div>Image: {p.image ? "Yes" : "No"}</div>
                      </div>
                      <div className="detail-span">
                        {p.description ? p.description : "No description"}
                      </div>
                    </div>
                  )}
                </div>
              )})
            )}
          </div>
        )}
      </section>

)}

      {showUsers && (
<section className="panel">
        <div className="panel-head">
          <h2>Users</h2>
          <div className="actions">
            <button className="ghost" onClick={handleUserImport} disabled={userImporting}>
              Import Users CSV
              {userImporting && <span className="spinner" />}
            </button>
            <button
              className="ghost"
              onClick={handleUsersBulkSync}
              disabled={usersBulkSyncing}
            >
              Sync Users
              {usersBulkSyncing && <span className="spinner" />}
            </button>
          </div>
        </div>
        <div className="grid space-top">
          <input
            value={userForm.id}
            onChange={(e) => setUserForm((u) => ({ ...u, id: e.target.value }))}
            placeholder="User ID"
          />
          <input
            value={userForm.first_name}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, first_name: e.target.value }))
            }
            placeholder="First name"
          />
          <input
            value={userForm.last_name}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, last_name: e.target.value }))
            }
            placeholder="Last name"
          />
          <input
            value={userForm.full_name}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, full_name: e.target.value }))
            }
            placeholder="Full name"
          />
          <input
            value={userForm.city}
            onChange={(e) => setUserForm((u) => ({ ...u, city: e.target.value }))}
            placeholder="City"
          />
          <input
            value={userForm.mobile}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, mobile: e.target.value }))
            }
            placeholder="Mobile"
          />
          <input
            value={userForm.dob}
            onChange={(e) => setUserForm((u) => ({ ...u, dob: e.target.value }))}
            placeholder="DOB"
          />
          <input
            value={userForm.gender}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, gender: e.target.value }))
            }
            placeholder="Gender"
          />
          <input
            value={userForm.policynum}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, policynum: e.target.value }))
            }
            placeholder="Policy number"
          />
          <input
            value={userForm.clntid}
            onChange={(e) =>
              setUserForm((u) => ({ ...u, clntid: e.target.value }))
            }
            placeholder="Client ID"
          />
        </div>
        <div className="actions space-top">
          <button className="primary" onClick={handleUserCreate}>
            Add / Update User
          </button>
        </div>

        <div className="hint block space-top">
          Supports queries like:
          <div className="hint-list">
            <div>city is rajshahi and age max 30</div>
            <div>father name mohib and age maximum 40</div>
            <div>nid contains 533 or mobile last 3 digit 002</div>
            <div>gender is female and city dhaka or city rajshahi</div>
          </div>
          <div className="hint-line">
            Parses AND within a group, and OR across groups.
          </div>
          <div className="hint-line">
            Applies numeric ranges (age), date ranges (dob, issue_date), suffix match for
            mobile, and partial text matches for all other fields.
          </div>
        </div>

        <div className="row space-top">
          <div className="input-wrap">
            <input
              value={userSemanticQuery}
              onChange={(e) => setUserSemanticQuery(e.target.value)}
              placeholder="Semantic search (e.g., Kamal from Rajshahi)"
            />
            {userSemanticQuery && (
              <button
                className="input-reset"
                onClick={handleUserSemanticReset}
                aria-label="Clear search"
                title="Clear"
              >
                ✕
              </button>
            )}
          </div>
          <button
            className="btn-soft btn-medium"
            onClick={handleUserSemanticSearch}
          >
            Semantic Search
          </button>
        </div>

        {userError && <span className="hint">{userError}</span>}

        <div className="table space-top">
          <div className="table-row header" style={{ gridTemplateColumns: userGridTemplate }}>
            <div>ID</div>
            <div>Name</div>
            <div>City</div>
            <div>Mobile</div>
            {userExtraCols.map((col) => (
              <div className="extra-col" key={col.key}>{col.label}</div>
            ))}
            <div>Actions</div>
          </div>
          {(userSemanticActive ? userSemanticResults : users).length === 0 ? (
            <div className="table-row empty">No users found.</div>
          ) : (
            (userSemanticActive ? userSemanticResults : users).map((u) => {
              const key = String(u.id);
              const name =
                u.full_name || [u.first_name, u.last_name].filter(Boolean).join(" ");
              return (
                <div key={key}>
                  <div className="table-row" style={{ gridTemplateColumns: userGridTemplate }}>
                    <div className="mono">{u.id}</div>
                    <div>{name || "-"}</div>
                    <div>{u.city || "-"}</div>
                    <div>{u.mobile || "-"}</div>
                    {userExtraCols.map((col) => (
                      <div className="extra-col" key={col.key}>{u[col.key] || "-"}</div>
                    ))}
                    <div className="actions">
                      <button className="ghost icon-button" onClick={() => toggleUserRow(key)}>
                        {userExpanded.has(key) ? "▾" : "▸"}
                      </button>
                      <button
                        className="ghost icon-button"
                        onClick={() => handleUserSync(key)}
                        title="Sync"
                        disabled={!!userSyncing[key]}
                      >
                        {userSyncing[key] ? <span className="spinner small" /> : "⟳"}
                      </button>
                      <button
                        className="ghost icon-button danger"
                        onClick={() => handleUserDelete(key)}
                        title="Delete"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                  {userExpanded.has(key) && (
                    <div className="table-row detail">
                      <div className="mono">Details</div>
                      <div className="detail-grid">
                        <div>Policy: {u.policynum || "-"}</div>
                        <div>Client ID: {u.clntid || "-"}</div>
                        <div>DOB: {u.dob || "-"}</div>
                        <div>Gender: {u.gender || "-"}</div>
                        <div>Address: {[u.addr1, u.addr2, u.city].filter(Boolean).join(", ") || "-"}</div>
                      </div>
                      <div className="detail-span">
                        Full Name: {u.full_name || name || "-"}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </section>
)}
    </div>
  );
}
