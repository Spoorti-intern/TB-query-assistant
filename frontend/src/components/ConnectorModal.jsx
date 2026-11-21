import { useState } from "react";
import { X, Database, Loader, CheckCircle, AlertCircle } from "lucide-react";
import { createConnector, testConnector, deleteConnector } from "../api";
import { toast } from "./Toast";

const defaultPorts = {
  postgresql: 5432,
  mysql: 3306,
  mongodb: 27017,
  supabase: 5432,
  mssql: 1433,
  sqlite: 0,
  oracle: 1521,
  mariadb: 3306,
  cockroachdb: 26257,
  redis: 6379,
  cassandra: 9042,
  neo4j: 7687,
  elasticsearch: 9200,
  clickhouse: 8123,
  influxdb: 8086,
  couchdb: 5984,
};

const defaultHosts = {
  postgresql: "localhost",
  mysql: "localhost",
  mongodb: "localhost",
  supabase: "db.xxxxx.supabase.co",
  mssql: "localhost",
  sqlite: "local",
  oracle: "localhost",
  mariadb: "localhost",
  cockroachdb: "localhost",
  redis: "localhost",
  cassandra: "localhost",
  neo4j: "localhost",
  elasticsearch: "localhost",
  clickhouse: "localhost",
  influxdb: "localhost",
  couchdb: "localhost",
};

const initialForm = {
  name: "",
  connector_type: "postgresql",
  host: "localhost",
  port: 5432,
  database: "",
  username: "",
  password: "",
};

export default function ConnectorModal({
  open,
  onClose,
  onCreated,
  connectors,
  onRefresh,
}) {
  const [form, setForm] = useState(initialForm);
  const [quickUri, setQuickUri] = useState("");
  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [view, setView] = useState("list"); // "list" | "form"

  if (!open) return null;

  const handleQuickConnect = async () => {
    if (!quickUri.trim()) return;
    setLoading(true);
    try {
      // Let the backend parse the URI via the connector API
      // We detect type from prefix
      let type = "postgresql";
      if (quickUri.startsWith("mysql://")) type = "mysql";
      else if (quickUri.match(/^mongodb(\+srv)?:\/\//)) type = "mongodb";
      else if (quickUri.includes("supabase")) type = "supabase";
      else if (quickUri.match(/^mssql(\+\w+)?:\/\//)) type = "mssql";
      else if (quickUri.startsWith("sqlite:")) type = "sqlite";
      else if (quickUri.match(/^oracle(\+\w+)?:\/\//)) type = "oracle";
      else if (quickUri.match(/^mariadb(\+\w+)?:\/\//)) type = "mariadb";
      else if (quickUri.match(/^cockroach(db)?:\/\//)) type = "cockroachdb";
      else if (quickUri.match(/^rediss?:\/\//)) type = "redis";
      else if (quickUri.startsWith("cassandra://")) type = "cassandra";
      else if (quickUri.match(/^(bolt|neo4j)(\+\w+)?:\/\//)) type = "neo4j";
      else if (quickUri.startsWith("elasticsearch://") || (quickUri.match(/^https?:\/\//) && quickUri.includes("9200"))) type = "elasticsearch";
      else if (quickUri.match(/^clickhouse(\+\w+)?:\/\//)) type = "clickhouse";
      else if (quickUri.startsWith("influxdb://")) type = "influxdb";
      else if (quickUri.startsWith("couchdb://")) type = "couchdb";

      const parsed = new URL(quickUri.replace("mongodb+srv://", "https://"));
      const data = {
        name: `${type} — ${parsed.pathname.replace("/", "") || "db"}@${parsed.hostname}`,
        connector_type: type,
        host: parsed.hostname,
        port: parsed.port ? Number(parsed.port) : defaultPorts[type],
        database: parsed.pathname.replace("/", "").split("?")[0] || "",
        username: parsed.username || "",
        password: parsed.password || "",
      };

      await createConnector(data);
      toast.success("Connector created!");
      setQuickUri("");
      if (onCreated) onCreated();
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to parse URI");
    } finally {
      setLoading(false);
    }
  };

  const handleTypeChange = (e) => {
    const type = e.target.value;
    setForm((prev) => ({
      ...prev,
      connector_type: type,
      host: defaultHosts[type] || "localhost",
      port: defaultPorts[type] || 5432,
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await createConnector({
        ...form,
        port: form.port === "" ? null : Number(form.port),
      });
      toast.success("Connector created!");
      setForm(initialForm);
      setView("list");
      if (onCreated) onCreated();
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create connector");
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (id) => {
    setTestingId(id);
    try {
      const result = await testConnector(id);
      setTestResults((p) => ({ ...p, [id]: { success: true, msg: result.message || "Connected!" } }));
      toast.success("Connection successful!");
      if (onRefresh) onRefresh();
    } catch (err) {
      setTestResults((p) => ({ ...p, [id]: { success: false, msg: err.response?.data?.detail || "Failed" } }));
      if (onRefresh) onRefresh();
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this connector?")) return;
    try {
      await deleteConnector(id);
      toast.success("Deleted");
      if (onRefresh) onRefresh();
    } catch (err) {
      toast.error("Failed to delete");
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{view === "form" ? "Add Connection" : "Connections"}</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {view === "list" ? (
          <>
            {/* Quick Connect */}
            <div className="quick-connect">
              <label className="quick-connect-label">Quick Connect — Paste a URI</label>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="quick-connect-input"
                  value={quickUri}
                  onChange={(e) => setQuickUri(e.target.value)}
                  placeholder="postgresql:// | mysql:// | redis:// | bolt:// | ..."
                  onKeyDown={(e) => e.key === "Enter" && handleQuickConnect()}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleQuickConnect}
                  disabled={loading || !quickUri.trim()}
                  style={{ flexShrink: 0 }}
                >
                  {loading ? <Loader size={14} className="spin" /> : "Connect"}
                </button>
              </div>
            </div>

            <div className="modal-divider">or</div>

            <button
              className="btn btn-secondary"
              onClick={() => setView("form")}
              style={{ width: "100%", marginBottom: 20 }}
            >
              Add Manually
            </button>

            {/* Existing connectors */}
            {connectors && connectors.length > 0 && (
              <>
                <div className="sidebar-section-label" style={{ marginBottom: 8 }}>
                  Existing Connections
                </div>
                {connectors.map((c) => (
                  <div
                    key={c.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "10px 12px",
                      borderRadius: 8,
                      background: "var(--bg-surface-2)",
                      marginBottom: 8,
                    }}
                  >
                    <Database size={16} style={{ color: "var(--accent-blue)", flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                        {c.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                        {c.connector_type} · {c.database} · {c.status}
                      </div>
                      {testResults[c.id] && (
                        <div
                          className={`test-result ${testResults[c.id].success ? "success" : "error"}`}
                          style={{ marginTop: 6 }}
                        >
                          {testResults[c.id].success ? (
                            <CheckCircle size={12} style={{ marginRight: 4 }} />
                          ) : (
                            <AlertCircle size={12} style={{ marginRight: 4 }} />
                          )}
                          {testResults[c.id].msg}
                        </div>
                      )}
                    </div>
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => handleTest(c.id)}
                      disabled={testingId === c.id}
                    >
                      {testingId === c.id ? <Loader size={12} className="spin" /> : "Test"}
                    </button>
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => handleDelete(c.id)}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </>
            )}
          </>
        ) : (
          /* Manual form */
          <form onSubmit={handleSubmit}>
            <div className="form-grid">
              <div className="form-field full">
                <label>Connector Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="My Database"
                  required
                />
              </div>
              <div className="form-field">
                <label>Database Type</label>
                <select value={form.connector_type} onChange={handleTypeChange}>
                  <optgroup label="Relational (SQL)">
                    <option value="postgresql">PostgreSQL</option>
                    <option value="mysql">MySQL</option>
                    <option value="mariadb">MariaDB</option>
                    <option value="mssql">SQL Server (MSSQL)</option>
                    <option value="sqlite">SQLite</option>
                    <option value="oracle">Oracle</option>
                    <option value="cockroachdb">CockroachDB</option>
                    <option value="supabase">Supabase (PostgreSQL)</option>
                  </optgroup>
                  <optgroup label="Document / NoSQL">
                    <option value="mongodb">MongoDB</option>
                    <option value="couchdb">CouchDB</option>
                    <option value="elasticsearch">Elasticsearch</option>
                  </optgroup>
                  <optgroup label="Key-Value / Cache">
                    <option value="redis">Redis</option>
                  </optgroup>
                  <optgroup label="Graph">
                    <option value="neo4j">Neo4j</option>
                  </optgroup>
                  <optgroup label="Wide Column">
                    <option value="cassandra">Cassandra</option>
                  </optgroup>
                  <optgroup label="Analytics / Time-Series">
                    <option value="clickhouse">ClickHouse</option>
                    <option value="influxdb">InfluxDB</option>
                  </optgroup>
                </select>
              </div>
              <div className="form-field">
                <label>Host</label>
                <input
                  value={form.host}
                  onChange={(e) => setForm((p) => ({ ...p, host: e.target.value }))}
                  placeholder="localhost"
                  required
                />
              </div>
              <div className="form-field">
                <label>Port</label>
                <input
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm((p) => ({ ...p, port: e.target.value === "" ? "" : Number(e.target.value) }))}
                />
              </div>
              <div className="form-field">
                <label>Database</label>
                <input
                  value={form.database}
                  onChange={(e) => setForm((p) => ({ ...p, database: e.target.value }))}
                  placeholder="my_database"
                  required
                />
              </div>
              <div className="form-field">
                <label>Username</label>
                <input
                  value={form.username}
                  onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
                  placeholder="user"
                />
              </div>
              <div className="form-field full">
                <label>Password</label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
                  placeholder="password"
                />
              </div>
            </div>

            <div className="modal-actions">
              <button type="submit" className="btn btn-primary" disabled={loading}>
                {loading ? "Saving..." : "Save Connection"}
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => { setView("list"); setForm(initialForm); }}
              >
                Back
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
