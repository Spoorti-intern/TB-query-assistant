import { useState, useEffect, useRef } from "react";
import { Database, Zap, Menu, ArrowRight } from "lucide-react";

// Map connector types to display info
const DB_TYPE_INFO = {
  postgresql: { label: "PostgreSQL", color: "#336791" },
  mysql: { label: "MySQL", color: "#4479A1" },
  mongodb: { label: "MongoDB", color: "#47A248" },
  supabase: { label: "Supabase", color: "#3ECF8E" },
  mssql: { label: "SQL Server", color: "#CC2927" },
  sqlite: { label: "SQLite", color: "#003B57" },
  oracle: { label: "Oracle", color: "#F80000" },
  mariadb: { label: "MariaDB", color: "#003545" },
  cockroachdb: { label: "CockroachDB", color: "#6933FF" },
  redis: { label: "Redis", color: "#DC382D" },
  cassandra: { label: "Cassandra", color: "#1287B1" },
  neo4j: { label: "Neo4j", color: "#008CC1" },
  elasticsearch: { label: "Elasticsearch", color: "#FEC514" },
  clickhouse: { label: "ClickHouse", color: "#FFCC00" },
  influxdb: { label: "InfluxDB", color: "#22ADF6" },
  couchdb: { label: "CouchDB", color: "#E42528" },
};

function getDbInfo(type) {
  return DB_TYPE_INFO[type?.toLowerCase()] || { label: type || "Database", color: "#666" };
}

export default function Topbar({ title, onToggleSidebar, activeConnector, detectReason }) {
  const dbInfo = activeConnector ? getDbInfo(activeConnector.connector_type) : null;
  const isConnected = activeConnector?.status === "connected";
  const [flash, setFlash] = useState(false);
  const prevConnectorId = useRef(activeConnector?.id);

  // Flash animation when active connector changes (auto-detected or link pasted)
  useEffect(() => {
    if (activeConnector?.id && activeConnector.id !== prevConnectorId.current) {
      prevConnectorId.current = activeConnector.id;
      setFlash(true);
      const timer = setTimeout(() => setFlash(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [activeConnector?.id]);

  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-toggle" onClick={onToggleSidebar} title="Toggle sidebar">
          <Menu size={18} />
        </button>
        <span className="topbar-title">{title || "New Chat"}</span>
      </div>

      <div className="topbar-right">
        {activeConnector ? (
          <div
            className={`topbar-db-badge ${flash ? "topbar-db-badge--flash" : ""}`}
            title={detectReason || `Connected to ${activeConnector.name}`}
          >
            <span
              className="topbar-db-status"
              style={{ background: isConnected ? "var(--accent-green)" : "var(--accent-red)" }}
            />
            <Database size={13} style={{ color: dbInfo.color }} />
            <span className="topbar-db-name">{activeConnector.name}</span>
            <span
              className="topbar-db-type"
              style={{
                background: dbInfo.color + "22",
                color: dbInfo.color,
                border: `1px solid ${dbInfo.color}44`,
              }}
            >
              {dbInfo.label}
            </span>
            {flash && detectReason && (
              <span className="topbar-db-detect-reason">
                <ArrowRight size={10} />
                {detectReason}
              </span>
            )}
          </div>
        ) : (
          <div className="topbar-db-badge topbar-db-badge--empty">
            <Database size={13} style={{ opacity: 0.4 }} />
            <span className="topbar-db-name" style={{ opacity: 0.5 }}>Auto-detect on query</span>
          </div>
        )}

        <div className="topbar-badge">
          <Zap size={12} />
          AI Agent
        </div>
      </div>
    </header>
  );
}
