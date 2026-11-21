import { useEffect, useState, useCallback, useRef } from "react";
import { getConnectors, getConnectorSchema, getSessions, createSession, deleteSession, getSession, updateSession, generateSessionTitle, testConnector } from "./api";

import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import ToastContainer from "./components/Toast";
import ConnectorModal from "./components/ConnectorModal";
import ChatPage from "./pages/ChatPage";

import "./App.css";

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [connectors, setConnectors] = useState([]);
  const [selectedConnectorId, setSelectedConnectorId] = useState("");
  const [connectorModalOpen, setConnectorModalOpen] = useState(false);
  const [detectReason, setDetectReason] = useState("");
  const [testingConnectors, setTestingConnectors] = useState({});

  // Chat sessions
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);

  // Fetch connectors
  const fetchConnectors = useCallback(async () => {
    try {
      const data = await getConnectors();
      setConnectors(data);
      return data;
    } catch (error) {
      console.error("Unable to fetch connectors:", error);
      return [];
    }
  }, []);

  // Auto-test all connectors that aren't "connected"
  const autoTestConnectors = useCallback(async (connectorList) => {
    const toTest = connectorList.filter((c) => c.status !== "connected");
    if (toTest.length === 0) return;

    // Mark all as testing
    const testingMap = {};
    toTest.forEach((c) => { testingMap[c.id] = true; });
    setTestingConnectors(testingMap);

    // Test in parallel
    const results = await Promise.allSettled(
      toTest.map(async (c) => {
        try {
          await testConnector(c.id);
          setTestingConnectors((prev) => { const n = { ...prev }; delete n[c.id]; return n; });
          return { id: c.id, status: "connected" };
        } catch {
          setTestingConnectors((prev) => { const n = { ...prev }; delete n[c.id]; return n; });
          return { id: c.id, status: "connection_failed" };
        }
      })
    );

    // Update connector statuses locally
    setConnectors((prev) =>
      prev.map((c) => {
        const result = results.find(
          (r) => r.status === "fulfilled" && r.value.id === c.id
        );
        if (result) {
          return { ...c, status: result.value.status };
        }
        return c;
      })
    );
  }, []);

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    try {
      const data = await getSessions();
      setSessions(data);
    } catch {
      setSessions([]);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      const data = await fetchConnectors();
      fetchSessions();
      // Auto-test all connectors on load
      if (data.length > 0) {
        autoTestConnectors(data);
      }
    };
    init();
  }, [fetchConnectors, fetchSessions, autoTestConnectors]);

  // Table names for dynamic suggestions
  const [tableNames, setTableNames] = useState([]);

  // Auto-select first connected connector
  useEffect(() => {
    if (!selectedConnectorId && connectors.length) {
      const first = connectors.find((c) => c.status === "connected");
      if (first) setSelectedConnectorId(String(first.id));
    }
  }, [connectors, selectedConnectorId]);

  // Fetch table names when active connector changes
  useEffect(() => {
    if (!selectedConnectorId) {
      setTableNames([]);
      return;
    }
    let cancelled = false;
    getConnectorSchema(selectedConnectorId)
      .then((schema) => {
        if (cancelled) return;
        let names = [];
        if (Array.isArray(schema.table_names)) {
          names = schema.table_names;
        } else if (Array.isArray(schema.tables)) {
          names = schema.tables.map((t) => t.table_name || t.name || "");
        } else if (schema.tables && typeof schema.tables === "object") {
          names = Object.keys(schema.tables);
        } else if (schema.collections && typeof schema.collections === "object") {
          names = Object.keys(schema.collections);
        }
        const SYSTEM_TABLES = new Set([
          "spt_fallback_db", "spt_fallback_dev", "spt_fallback_usd", "spt_monitor",
          "spt_values", "MSreplication_options", "MSreplication_subscriptions",
          "sysdiagrams", "dtproperties", "sysconstraints", "syssegments",
          "trace_xe_action_map", "trace_xe_event_map",
        ]);
        names = names.filter((n) => n && !SYSTEM_TABLES.has(n) && !n.startsWith("sys"));
        if (Array.isArray(schema.tables_with_data) && schema.tables_with_data.length > 0) {
          const withData = new Set(schema.tables_with_data);
          names.sort((a, b) => (withData.has(b) ? 1 : 0) - (withData.has(a) ? 1 : 0));
        }
        setTableNames(names);
      })
      .catch(() => {
        if (!cancelled) setTableNames([]);
      });
    return () => { cancelled = true; };
  }, [selectedConnectorId]);

  // Auto-save messages to session when a response finishes
  const saveTimerRef = useRef(null);
  const titleGeneratedRef = useRef(new Set());
  useEffect(() => {
    if (!currentSessionId || messages.length === 0) return;
    const stillStreaming = messages.some(
      (m) => m.status === "streaming" || m.status === "thinking" || m.status === "tool_running"
    );
    if (stillStreaming) return;

    clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      const toSave = messages.map((m) => ({
        role: m.role,
        content: m.content || "",
        status: m.status === "done" ? "done" : m.status === "error" ? "error" : "done",
        steps: m.steps || [],
      }));
      await updateSession(currentSessionId, { messages: toSave }).catch(() => {});

      const hasAssistant = messages.some((m) => m.role === "assistant" && m.content);
      const hasUser = messages.some((m) => m.role === "user" && m.content);
      if (hasUser && hasAssistant && !titleGeneratedRef.current.has(currentSessionId)) {
        titleGeneratedRef.current.add(currentSessionId);
        try {
          const updated = await generateSessionTitle(currentSessionId, toSave);
          if (updated?.title) {
            setSessions((prev) =>
              prev.map((s) => (s.id === currentSessionId ? { ...s, title: updated.title } : s))
            );
          }
        } catch {
          // Title generation is non-critical
        }
      }
    }, 500);

    return () => clearTimeout(saveTimerRef.current);
  }, [messages, currentSessionId]);

  // New chat
  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
  };

  // Select a session
  const handleSelectSession = async (sessionId) => {
    setCurrentSessionId(sessionId);
    try {
      const session = await getSession(sessionId);
      if (session?.messages?.length > 0) {
        const restored = session.messages.map((m) => ({
          role: m.role,
          content: m.content || "",
          status: m.status || "done",
          steps: m.steps || [],
          statusMessages: [],
          toolResults: [],
        }));
        setMessages(restored);
      } else {
        setMessages([]);
      }
    } catch {
      const cached = sessions.find((s) => s.id === sessionId);
      if (cached?.messages?.length > 0) {
        setMessages(cached.messages);
      } else {
        setMessages([]);
      }
    }
  };

  // Delete a session
  const handleDeleteSession = async (sessionId) => {
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setMessages([]);
      }
    } catch {
      // Session API might not exist yet
    }
  };

  // Called when user sends first message in a new chat
  const handleFirstMessage = async (text) => {
    try {
      const title = text.length > 40 ? text.slice(0, 40) + "..." : text;
      const session = await createSession({ title });
      setCurrentSessionId(session.id);
      setSessions((prev) => [session, ...prev]);
    } catch {
      // Session API might not exist yet
    }
  };

  // Rename a session
  const handleRenameSession = async (sessionId, newTitle) => {
    try {
      await updateSession(sessionId, { title: newTitle });
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: newTitle } : s))
      );
    } catch {
      // Rename failed silently
    }
  };

  const currentSession = sessions.find((s) => s.id === currentSessionId);
  const chatTitle = currentSession?.title || (messages.length > 0 ? "Chat" : "New Chat");

  return (
    <div className="app-shell">
      <ToastContainer />

      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
        connectors={connectors}
        selectedConnectorId={selectedConnectorId}
        onSelectConnector={(id) => setSelectedConnectorId(id)}
        onAddConnection={() => setConnectorModalOpen(true)}
        testingConnectors={testingConnectors}
      />

      {/* Mobile backdrop */}
      {!sidebarCollapsed && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarCollapsed(true)}
          style={{ display: "none" }}
        />
      )}

      <main className="app-main">
        <Topbar
          title={chatTitle}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
          activeConnector={connectors.find((c) => String(c.id) === String(selectedConnectorId))}
          detectReason={detectReason}
        />

        <ChatPage
          connectors={connectors}
          selectedConnectorId={selectedConnectorId}
          onSelectConnector={setSelectedConnectorId}
          onConnectorAdded={fetchConnectors}
          messages={messages}
          setMessages={setMessages}
          onFirstMessage={handleFirstMessage}
          tableNames={tableNames}
          onDetectReason={setDetectReason}
        />
      </main>

      <ConnectorModal
        open={connectorModalOpen}
        onClose={() => setConnectorModalOpen(false)}
        onCreated={fetchConnectors}
        connectors={connectors}
        onRefresh={fetchConnectors}
      />
    </div>
  );
}

export default App;
