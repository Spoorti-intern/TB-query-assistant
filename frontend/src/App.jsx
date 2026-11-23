import { useEffect, useState, useCallback, useRef } from "react";
import { getConnectors, getConnectorSchema, getSessions, createSession, deleteSession, getSession, updateSession, generateSessionTitle, testConnector, getMe, useCredit, getCredits } from "./api";
import { Database, CreditCard, ArrowRight, X, Sparkles, Crown, PartyPopper } from "lucide-react";

import Sidebar from "./components/Sidebar";
import Topbar from "./components/Topbar";
import ToastContainer from "./components/Toast";
import ConnectorModal from "./components/ConnectorModal";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";
import LandingPage from "./pages/LandingPage";
import PaymentPage from "./pages/PaymentPage";
import AdminPage from "./pages/AdminPage";

import "./App.css";

function PaymentWallModal({ onUpgrade, onDismiss }) {
  return (
    <div className="payment-wall-overlay" onClick={onDismiss}>
      <div className="payment-wall-modal" onClick={(e) => e.stopPropagation()}>
        <button className="payment-wall-close" onClick={onDismiss}>
          <X size={16} />
        </button>

        <div className="payment-wall-icon">
          <Crown size={32} />
        </div>

        <h2>Upgrade to Pro</h2>
        <p>
          You&apos;ve used your 2 free queries. Upgrade to Pro to unlock
          unlimited database queries and full chat history.
        </p>

        <div className="payment-wall-price">
          <span className="payment-wall-amount">$9.99</span>
          <span className="payment-wall-period">/ 50 credits</span>
        </div>

        <div className="payment-wall-features">
          <div className="payment-wall-feature">
            <Sparkles size={13} />
            50 query credits
          </div>
          <div className="payment-wall-feature">
            <Database size={13} />
            Full chat history
          </div>
          <div className="payment-wall-feature">
            <CreditCard size={13} />
            Secure payment
          </div>
        </div>

        <button className="payment-wall-btn" onClick={onUpgrade}>
          Upgrade Now <ArrowRight size={14} />
        </button>

        <button className="payment-wall-dismiss" onClick={onDismiss}>
          Maybe later
        </button>
      </div>
    </div>
  );
}

function WelcomeGreeting({ user, onDismiss }) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onDismiss, 500);
    }, 3500);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  const hour = new Date().getHours();
  let timeGreeting = "Good evening";
  if (hour < 12) timeGreeting = "Good morning";
  else if (hour < 17) timeGreeting = "Good afternoon";

  return (
    <div className={`welcome-overlay ${visible ? "welcome-visible" : "welcome-hidden"}`}>
      <div className="welcome-content">
        <div className="welcome-icon">
          <PartyPopper size={40} />
        </div>
        <h1 className="welcome-title">{timeGreeting},</h1>
        <h2 className="welcome-name">{user?.username || "there"}!</h2>
        <p className="welcome-subtitle">Welcome to Query Ops. Let&apos;s build something amazing.</p>
        <div className="welcome-dots">
          <span className="welcome-dot welcome-dot-1" />
          <span className="welcome-dot welcome-dot-2" />
          <span className="welcome-dot welcome-dot-3" />
        </div>
      </div>
    </div>
  );
}

function App() {
  // Auth state
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [showLogin, setShowLogin] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);

  // Payment state
  const [showPayment, setShowPayment] = useState(false);
  const [showPaymentWall, setShowPaymentWall] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [credits, setCredits] = useState(2);
  const [hasPaid, setHasPaid] = useState(false);

  // Check for existing token on mount
  useEffect(() => {
    const token = localStorage.getItem("qops_token");
    if (token) {
      getMe()
        .then((userData) => {
          setUser(userData);
          setCredits(userData.credits ?? 2);
          setHasPaid(userData.has_paid ?? false);
          setAuthLoading(false);
        })
        .catch(() => {
          localStorage.removeItem("qops_token");
          localStorage.removeItem("qops_user");
          setAuthLoading(false);
        });
    } else {
      setAuthLoading(false);
    }
  }, []);

  const handleLogin = (result) => {
    localStorage.setItem("qops_token", result.access_token);
    localStorage.setItem("qops_user", JSON.stringify(result.user));
    setUser(result.user);
    setCredits(result.user.credits ?? 2);
    setHasPaid(result.user.has_paid ?? false);
    setShowLogin(false);
    setShowWelcome(true);
  };

  const handleLogout = () => {
    localStorage.removeItem("qops_token");
    localStorage.removeItem("qops_user");
    setUser(null);
    setShowLogin(false);
    setShowPayment(false);
    setShowAdmin(false);
  };

  const handleUseCredit = async () => {
    try {
      const result = await useCredit();
      setCredits(result.credits);
      setHasPaid(result.has_paid);
      return true;
    } catch {
      // No credits left — show payment wall
      setShowPaymentWall(true);
      return false;
    }
  };

  const handlePaymentSuccess = (paymentResult) => {
    // Update credits after payment
    setCredits((prev) => prev + (paymentResult.credits_added || 50));
    setHasPaid(true);
    setShowPayment(false);
    // Refresh user data
    getMe().then((userData) => {
      setUser(userData);
      setCredits(userData.credits);
      setHasPaid(userData.has_paid);
    }).catch(() => {});
  };

  const handleGoToPayment = () => {
    setShowPaymentWall(false);
    setShowPayment(true);
  };

  // Show loading while checking auth
  if (authLoading) {
    return (
      <div className="auth-loading">
        <div className="auth-loading-spinner" />
      </div>
    );
  }

  // Show landing page if not logged in
  if (!user && !showLogin) {
    return (
      <LandingPage onGetStarted={() => setShowLogin(true)} />
    );
  }

  // Show login/register
  if (!user && showLogin) {
    return <LoginPage onLogin={handleLogin} />;
  }

  // Show payment page
  if (showPayment) {
    return (
      <PaymentPage
        user={user}
        onSuccess={handlePaymentSuccess}
        onBack={() => setShowPayment(false)}
      />
    );
  }

  // Show admin page
  if (showAdmin) {
    return (
      <AdminPage
        user={user}
        onBack={() => setShowAdmin(false)}
        onLogout={handleLogout}
      />
    );
  }

  // Logged in — show the app
  return (
    <>
      {showWelcome && (
        <WelcomeGreeting
          user={user}
          onDismiss={() => setShowWelcome(false)}
        />
      )}
      <AppShell
        user={user}
        onLogout={handleLogout}
        credits={credits}
        hasPaid={hasPaid}
        onUseCredit={handleUseCredit}
        onUpgrade={() => setShowPayment(true)}
        onShowAdmin={() => setShowAdmin(true)}
      />
      {showPaymentWall && (
        <PaymentWallModal
          onUpgrade={handleGoToPayment}
          onDismiss={() => setShowPaymentWall(false)}
        />
      )}
    </>
  );
}

function AppShell({ user, onLogout, credits, hasPaid, onUseCredit, onUpgrade, onShowAdmin }) {
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

    const testingMap = {};
    toTest.forEach((c) => { testingMap[c.id] = true; });
    setTestingConnectors(testingMap);

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

  const handleNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
  };

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
        user={user}
        onLogout={onLogout}
        credits={credits}
        hasPaid={hasPaid}
        onUpgrade={onUpgrade}
        onShowAdmin={onShowAdmin}
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
          user={user}
          onLogout={onLogout}
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
          credits={credits}
          hasPaid={hasPaid}
          onUseCredit={onUseCredit}
          onUpgrade={onUpgrade}
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
