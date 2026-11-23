import { Plus, Database, PanelLeftClose, LogOut, CreditCard, Crown, Settings, Link } from "lucide-react";

export default function Sidebar({
  collapsed,
  onToggle,
  onNewChat,
  onNewConnection,
  user,
  onLogout,
  credits = 0,
  onUpgrade,
  onShowAdmin,
}) {
  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <div className="sidebar-logo">
            <Database size={16} />
          </div>
          <span className="sidebar-brand-text">Query Ops</span>
        </div>
        <button className="sidebar-toggle" onClick={onToggle} title="Collapse sidebar">
          <PanelLeftClose size={16} />
        </button>
      </div>

      <button className="new-chat-btn" onClick={onNewChat}>
        <Plus size={16} />
        New Chat
      </button>

      <button className="new-chat-btn" onClick={onNewConnection} style={{ marginTop: 4, background: "var(--bg-surface-2)" }}>
        <Link size={16} />
        New Connection
      </button>

      {/* Credits indicator */}
      {user && (
        <div className="sidebar-credits">
          <div className="sidebar-credits-bar">
            <CreditCard size={13} />
            <span className="sidebar-credits-label">Credits</span>
            <span className={`sidebar-credits-count ${credits <= 0 ? "empty" : ""}`}>
              {credits}
            </span>
          </div>
          {credits <= 0 && (
            <button className="sidebar-upgrade-btn" onClick={onUpgrade}>
              <Crown size={12} /> Buy Credits
            </button>
          )}
        </div>
      )}

      {/* Spacer to push profile to bottom */}
      <div style={{ flex: 1 }} />

      {/* User section at bottom */}
      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-avatar">
            {user.username?.[0]?.toUpperCase() || "U"}
          </div>
          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{user.username}</span>
            <span className="sidebar-user-email">{user.email}</span>
          </div>
          <div className="sidebar-user-actions">
            {user.is_admin && (
              <button className="sidebar-admin-btn" onClick={onShowAdmin} title="Admin Dashboard">
                <Settings size={14} />
              </button>
            )}
            <button className="sidebar-user-logout" onClick={onLogout} title="Sign out">
              <LogOut size={14} />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
