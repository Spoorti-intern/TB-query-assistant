import { Zap, Menu, LogOut } from "lucide-react";

export default function Topbar({ title, onToggleSidebar, user, onLogout }) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="topbar-toggle" onClick={onToggleSidebar} title="Toggle sidebar">
          <Menu size={18} />
        </button>
        <span className="topbar-title">{title || "New Chat"}</span>
      </div>

      <div className="topbar-right">
        <div className="topbar-badge">
          <Zap size={12} />
          AI Agent
        </div>

        {user && (
          <div className="topbar-user">
            <span className="topbar-user-avatar">
              {user.username?.[0]?.toUpperCase() || "U"}
            </span>
            <button className="topbar-logout" onClick={onLogout} title="Sign out">
              <LogOut size={14} />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
