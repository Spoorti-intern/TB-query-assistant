import { useState, useEffect } from "react";
import { Plus, Database, MessageSquare, X, PanelLeftClose, Pencil, Check, Loader, ChevronDown, ChevronUp } from "lucide-react";

const DB_TYPE_COLORS = {
  postgresql: "#336791",
  mysql: "#4479A1",
  mongodb: "#47A248",
  supabase: "#3ECF8E",
  mssql: "#CC2927",
  sqlite: "#003B57",
  oracle: "#F80000",
  mariadb: "#003545",
  cockroachdb: "#6933FF",
  redis: "#DC382D",
  cassandra: "#1287B1",
  neo4j: "#008CC1",
  elasticsearch: "#FEC514",
  clickhouse: "#FFCC00",
  influxdb: "#22ADF6",
  couchdb: "#E42528",
};

const DB_TYPE_LABELS = {
  postgresql: "PostgreSQL",
  mysql: "MySQL",
  mongodb: "MongoDB",
  supabase: "Supabase",
  mssql: "SQL Server",
  sqlite: "SQLite",
  oracle: "Oracle",
  mariadb: "MariaDB",
  cockroachdb: "CockroachDB",
  redis: "Redis",
  cassandra: "Cassandra",
  neo4j: "Neo4j",
  elasticsearch: "Elasticsearch",
  clickhouse: "ClickHouse",
  influxdb: "InfluxDB",
  couchdb: "CouchDB",
};

export default function Sidebar({
  collapsed,
  onToggle,
  sessions,
  currentSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
  connectors = [],
  selectedConnectorId,
  onSelectConnector,
  onAddConnection,
  testingConnectors = {},
}) {
  const [dbPanelOpen, setDbPanelOpen] = useState(true);

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const groups = { today: [], yesterday: [], older: [] };

  (sessions || []).forEach((s) => {
    const d = new Date(s.updated_at || s.created_at);
    if (d >= today) groups.today.push(s);
    else if (d >= yesterday) groups.yesterday.push(s);
    else groups.older.push(s);
  });

  const connectedCount = connectors.filter((c) => c.status === "connected").length;
  const activeConnector = connectors.find((c) => String(c.id) === String(selectedConnectorId));

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <Database size={16} />
          </div>
          <span className="sidebar-brand-text">TB Query</span>
        </div>
        <button className="sidebar-toggle" onClick={onToggle} title="Collapse sidebar">
          <PanelLeftClose size={16} />
        </button>
      </div>

      <button className="new-chat-btn" onClick={onNewChat}>
        <Plus size={16} />
        New Chat
      </button>

      {/* ── DATABASE CONNECTIONS PANEL ── */}
      <div className="sidebar-db-panel">
        <button
          className="sidebar-db-panel-header"
          onClick={() => setDbPanelOpen(!dbPanelOpen)}
        >
          <Database size={13} />
          <span className="sidebar-db-panel-title">Connections</span>
          <span className="sidebar-db-panel-count">
            {connectedCount}/{connectors.length}
          </span>
          {dbPanelOpen ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>

        {dbPanelOpen && (
          <div className="sidebar-db-list">
            {connectors.length === 0 ? (
              <div className="sidebar-db-empty">
                No databases connected
              </div>
            ) : (
              connectors.map((c) => {
                const isActive = String(c.id) === String(selectedConnectorId);
                const isConnected = c.status === "connected";
                const isTesting = testingConnectors[c.id];
                const color = DB_TYPE_COLORS[c.connector_type?.toLowerCase()] || "#666";
                const label = DB_TYPE_LABELS[c.connector_type?.toLowerCase()] || c.connector_type;

                return (
                  <div
                    key={c.id}
                    className={`sidebar-db-item ${isActive ? "active" : ""}`}
                    title={`${c.name} — ${label} — ${isConnected ? "Connected" : "Disconnected"}`}
                    onClick={() => onSelectConnector && onSelectConnector(String(c.id))}
                    style={{ cursor: "pointer" }}
                  >
                    <span
                      className="sidebar-db-dot"
                      style={{
                        background: isTesting
                          ? "var(--accent-orange)"
                          : isConnected
                          ? "var(--accent-green)"
                          : "var(--accent-red)",
                      }}
                    />
                    <Database size={13} style={{ color, flexShrink: 0 }} />
                    <span className="sidebar-db-item-name">{c.name}</span>
                    <span
                      className="sidebar-db-item-type"
                      style={{
                        background: color + "22",
                        color: color,
                        border: `1px solid ${color}44`,
                      }}
                    >
                      {label}
                    </span>
                    {isTesting && <Loader size={11} className="spin" />}
                  </div>
                );
              })
            )}

            <button className="sidebar-db-add" onClick={onAddConnection}>
              <Plus size={13} />
              Add Connection
            </button>
          </div>
        )}
      </div>

      {/* ── Active DB indicator ── */}
      {activeConnector && (
        <div className="sidebar-active-db">
          <span
            className="sidebar-db-dot"
            style={{
              background: activeConnector.status === "connected"
                ? "var(--accent-green)"
                : "var(--accent-red)",
            }}
          />
          <span className="sidebar-active-db-label">Active:</span>
          <span className="sidebar-active-db-name">{activeConnector.name}</span>
        </div>
      )}

      <div className="sidebar-history">
        {groups.today.length > 0 && (
          <div className="sidebar-history-group">
            <div className="sidebar-section-label">Today</div>
            {groups.today.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === currentSessionId}
                onSelect={() => onSelectSession(s.id)}
                onDelete={() => onDeleteSession(s.id)}
                onRename={(title) => onRenameSession(s.id, title)}
              />
            ))}
          </div>
        )}

        {groups.yesterday.length > 0 && (
          <div className="sidebar-history-group">
            <div className="sidebar-section-label">Yesterday</div>
            {groups.yesterday.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === currentSessionId}
                onSelect={() => onSelectSession(s.id)}
                onDelete={() => onDeleteSession(s.id)}
                onRename={(title) => onRenameSession(s.id, title)}
              />
            ))}
          </div>
        )}

        {groups.older.length > 0 && (
          <div className="sidebar-history-group">
            <div className="sidebar-section-label">Previous</div>
            {groups.older.map((s) => (
              <SessionItem
                key={s.id}
                session={s}
                active={s.id === currentSessionId}
                onSelect={() => onSelectSession(s.id)}
                onDelete={() => onDeleteSession(s.id)}
                onRename={(title) => onRenameSession(s.id, title)}
              />
            ))}
          </div>
        )}

        {(!sessions || sessions.length === 0) && (
          <div style={{ padding: "12px 8px", color: "var(--text-tertiary)", fontSize: 12 }}>
            No conversations yet
          </div>
        )}
      </div>
    </aside>
  );
}

function SessionItem({ session, active, onSelect, onDelete, onRename }) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");

  const handleStartEdit = (e) => {
    e.stopPropagation();
    setEditTitle(session.title || "New Chat");
    setEditing(true);
  };

  const handleSaveEdit = (e) => {
    e.stopPropagation();
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== session.title) {
      onRename(trimmed);
    }
    setEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleSaveEdit(e);
    } else if (e.key === "Escape") {
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <div className={`history-item ${active ? "active" : ""}`} style={{ cursor: "default" }}>
        <MessageSquare size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
        <input
          className="history-item-rename-input"
          value={editTitle}
          onChange={(e) => setEditTitle(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={handleSaveEdit}
          autoFocus
          onClick={(e) => e.stopPropagation()}
        />
        <span
          className="history-item-action"
          onClick={handleSaveEdit}
          title="Save"
        >
          <Check size={12} />
        </span>
      </div>
    );
  }

  return (
    <button className={`history-item ${active ? "active" : ""}`} onClick={onSelect}>
      <MessageSquare size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
      <span className="history-item-text">{session.title || "New Chat"}</span>
      <span className="history-item-actions">
        <span
          className="history-item-action"
          onClick={handleStartEdit}
          title="Rename"
        >
          <Pencil size={11} />
        </span>
        <span
          className="history-item-action"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          title="Delete"
        >
          <X size={12} />
        </span>
      </span>
    </button>
  );
}
