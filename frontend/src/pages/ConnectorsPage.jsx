import { useState } from "react";
import {
  Database,
  Plus,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import {
  createConnector,
  testConnector,
  deleteConnector,
  getConnectorSchema,
} from "../api";
import { toast } from "../components/Toast";

const initialForm = {
  name: "",
  connector_type: "postgresql",
  host: "localhost",
  port: 5432,
  database: "",
  username: "",
  password: "",
};

const defaultPorts = {
  postgresql: 5432,
  mysql: 3306,
  mongodb: 27017,
  supabase: 5432,
};

const defaultHosts = {
  postgresql: "localhost",
  mysql: "localhost",
  mongodb: "localhost",
  supabase: "db.xxxxx.supabase.co",
};

const defaultUsernames = {
  postgresql: "",
  mysql: "",
  mongodb: "",
  supabase: "postgres",
};

export default function ConnectorsPage({ connectors, onRefresh }) {
  const [form, setForm] = useState(initialForm);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);

  const [testingConnector, setTestingConnector] = useState("");
  const [testResults, setTestResults] = useState({});
  const [schemaResults, setSchemaResults] = useState({});
  const [loadingSchema, setLoadingSchema] = useState("");

  const handleFormChange = (event) => {
    const { name, value } = event.target;

    if (name === "connector_type") {
      setForm((prev) => ({
        ...prev,
        connector_type: value,
        port: defaultPorts[value] || "",
        host: defaultHosts[value] || "localhost",
        username: defaultUsernames[value] || prev.username,
      }));
      return;
    }

    setForm((prev) => ({
      ...prev,
      [name]: name === "port" ? (value === "" ? "" : Number(value)) : value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      setLoading(true);
      await createConnector({
        ...form,
        port: form.port === "" ? null : Number(form.port),
      });
      setForm({ ...initialForm });
      setShowForm(false);
      await onRefresh();
      toast.success("Connector created successfully!");
    } catch (error) {
      toast.error(
        error.response?.data?.detail || "Unable to create connector."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (connectorId) => {
    try {
      setTestingConnector(connectorId);
      const result = await testConnector(connectorId);
      setTestResults((prev) => ({
        ...prev,
        [connectorId]: {
          success: true,
          message: result.message || "Connection successful!",
        },
      }));
      toast.success("Connection successful!");
      await onRefresh();
    } catch (error) {
      setTestResults((prev) => ({
        ...prev,
        [connectorId]: {
          success: false,
          message: error.response?.data?.detail || "Connection failed.",
        },
      }));
      toast.error(error.response?.data?.detail || "Connection failed.");
      await onRefresh();
    } finally {
      setTestingConnector("");
    }
  };

  const handleViewSchema = async (connectorId) => {
    try {
      setLoadingSchema(connectorId);
      const result = await getConnectorSchema(connectorId);
      setSchemaResults((prev) => ({ ...prev, [connectorId]: result }));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Schema discovery failed.");
    } finally {
      setLoadingSchema("");
    }
  };

  const handleDelete = async (connectorId) => {
    if (!window.confirm("Are you sure you want to delete this connector?")) return;

    try {
      await deleteConnector(connectorId);
      setTestResults((prev) => {
        const updated = { ...prev };
        delete updated[connectorId];
        return updated;
      });
      setSchemaResults((prev) => {
        const updated = { ...prev };
        delete updated[connectorId];
        return updated;
      });
      await onRefresh();
      toast.success("Connector deleted.");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Unable to delete connector.");
    }
  };

  return (
    <>
      <div className="tb-page-heading">
        <div>
          <h1>Data Connectors</h1>
          <p className="tb-muted">Configure and manage your database connections.</p>
        </div>
        <button className="tb-button" onClick={() => setShowForm(!showForm)}>
          {showForm ? <X size={16} /> : <Plus size={16} />}
          {showForm ? "Close" : "Add Connector"}
        </button>
      </div>

      {showForm && (
        <div className="tb-panel">
          <h3>Add a new connector</h3>
          <p className="tb-muted">Enter the database connection details.</p>

          <form onSubmit={handleSubmit}>
            <div className="tb-form-grid">
              <div className="tb-field">
                <label>Connector Name</label>
                <input name="name" value={form.name} onChange={handleFormChange} placeholder="My PostgreSQL Database" required />
              </div>
              <div className="tb-field">
                <label>Database Type</label>
                <select name="connector_type" value={form.connector_type} onChange={handleFormChange}>
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                  <option value="mongodb">MongoDB</option>
                  <option value="supabase">Supabase (PostgreSQL)</option>
                </select>
              </div>
              <div className="tb-field">
                <label>Host</label>
                <input name="host" value={form.host} onChange={handleFormChange} placeholder="localhost" required />
              </div>
              <div className="tb-field">
                <label>Port</label>
                <input type="number" name="port" value={form.port} onChange={handleFormChange} placeholder="5432" />
              </div>
              <div className="tb-field">
                <label>Database Name</label>
                <input name="database" value={form.database} onChange={handleFormChange} placeholder="database_name" required />
              </div>
              <div className="tb-field">
                <label>Username</label>
                <input name="username" value={form.username} onChange={handleFormChange} placeholder="Database username" />
              </div>
              <div className="tb-field">
                <label>Password</label>
                <input type="password" name="password" value={form.password} onChange={handleFormChange} placeholder="Database password" />
              </div>
            </div>

            <div className="tb-form-actions">
              <button type="submit" className="tb-button" disabled={loading}>
                {loading ? "Saving..." : "Save Connector"}
              </button>
              <button type="button" className="tb-button secondary" onClick={() => { setShowForm(false); setForm({ ...initialForm }); }}>
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="tb-panel">
        <h3>Registered Data Sources</h3>
        <p className="tb-muted">Your configured database connectors appear here.</p>

        {connectors.length === 0 ? (
          <div className="tb-empty">
            <Database size={28} />
            <p>No connectors added yet.</p>
            <p>Add a connector to get started.</p>
          </div>
        ) : (
          connectors.map((connector) => (
            <div className="tb-connector-row" key={connector.id}>
              <div className="tb-connector-info">
                <div className="tb-connector-icon">
                  <Database size={20} />
                </div>
                <div>
                  <div className="tb-connector-name">{connector.name}</div>
                  <div className="tb-connector-meta">
                    {connector.connector_type} · {connector.database} · Status: {connector.status}
                  </div>
                  {testResults[connector.id] && (
                    <div className={`tb-result ${testResults[connector.id].success ? "success" : "error"}`}>
                      {testResults[connector.id].message}
                    </div>
                  )}
                </div>
              </div>

              <div className="tb-connector-actions">
                <button className="tb-button" disabled={testingConnector === connector.id} onClick={() => handleTest(connector.id)}>
                  <ShieldCheck size={15} />
                  {testingConnector === connector.id ? "Testing..." : "Test Connection"}
                </button>
                <button className="tb-button secondary" disabled={loadingSchema === connector.id || connector.status !== "connected"} onClick={() => handleViewSchema(connector.id)}>
                  <Database size={15} />
                  {loadingSchema === connector.id ? "Loading Schema..." : "View Schema"}
                </button>
                <button className="tb-button danger" onClick={() => handleDelete(connector.id)} title="Delete connector">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {Object.entries(schemaResults).map(([connectorId, schema]) => (
        <div key={connectorId} className="tb-schema-panel">
          <h3>Database Schema: {schema.database || schema.database_name || "Connected database"}</h3>
          <p className="tb-muted">Database Type: {schema.connector_type || "Unknown"}</p>

          {Array.isArray(schema.tables) ? (
            <>
              <p className="tb-muted">Total Tables: {schema.total_tables ?? schema.tables.length}</p>
              {schema.tables.map((table, index) => (
                <div key={table.table_name || index} style={{ marginTop: 18 }}>
                  <h3>Table: {table.table_name || table.name || `Table ${index + 1}`}</h3>
                  <p className="tb-muted">
                    Primary Key: {Array.isArray(table.primary_key) ? table.primary_key.join(", ") || "None" : "Not provided"}
                  </p>
                  {(Array.isArray(table.columns) ? table.columns : []).map((col, ci) => (
                    <div key={col.column_name || col.name || ci} className="tb-schema-column">
                      <strong>{col.column_name || col.name}</strong>{" — "}
                      {col.data_type || col.type || "Unknown type"}{" · "}
                      {col.nullable === undefined ? "" : col.nullable ? "Nullable" : "Not Nullable"}
                    </div>
                  ))}
                </div>
              ))}
              {schema.tables.length === 0 && <p className="tb-muted">No tables found.</p>}
            </>
          ) : (
            <pre className="tb-sql-block">{JSON.stringify(schema, null, 2)}</pre>
          )}
        </div>
      ))}

      <p className="tb-muted">
        PostgreSQL, MySQL, MongoDB and Supabase PostgreSQL connectors are supported.
      </p>
    </>
  );
}
