import { useState, useEffect } from "react";
import {
  ArrowLeft,
  Users,
  CreditCard,
  Database,
  TrendingUp,
  Search,
  Plus,
  Loader,
  LogOut,
  Crown,
  DollarSign,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { getAdminUsers, getAdminTransactions, getAdminStats, allocateCredits } from "../api";

export default function AdminPage({ user, onBack, onLogout }) {
  const [tab, setTab] = useState("overview"); // overview | users | transactions
  const [users, setUsers] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [allocatingUser, setAllocatingUser] = useState(null);
  const [allocateAmount, setAllocateAmount] = useState("");
  const [allocateMsg, setAllocateMsg] = useState("");

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [statsData, usersData, txnData] = await Promise.all([
        getAdminStats(),
        getAdminUsers(),
        getAdminTransactions(),
      ]);
      setStats(statsData);
      setUsers(usersData);
      setTransactions(txnData);
    } catch (err) {
      console.error("Admin data fetch failed:", err);
    }
    setLoading(false);
  };

  const handleAllocate = async () => {
    if (!allocatingUser || !allocateAmount) return;
    try {
      const result = await allocateCredits(allocatingUser, parseInt(allocateAmount));
      setAllocateMsg(`Added ${allocateAmount} credits to ${result.username}`);
      setAllocatingUser(null);
      setAllocateAmount("");
      loadData();
      setTimeout(() => setAllocateMsg(""), 3000);
    } catch {
      setAllocateMsg("Failed to allocate credits");
      setTimeout(() => setAllocateMsg(""), 3000);
    }
  };

  const filteredUsers = users.filter(
    (u) =>
      u.username?.toLowerCase().includes(search.toLowerCase()) ||
      u.email?.toLowerCase().includes(search.toLowerCase())
  );

  const filteredTxns = transactions.filter(
    (t) =>
      t.username?.toLowerCase().includes(search.toLowerCase()) ||
      t.email?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className="admin-page">
        <div className="admin-loading">
          <Loader size={32} className="spin" />
          <p>Loading admin dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      {/* Top bar */}
      <header className="admin-topbar">
        <div className="admin-topbar-left">
          <button className="admin-back" onClick={onBack}>
            <ArrowLeft size={18} />
          </button>
          <div className="admin-brand">
            <Database size={18} />
            <span>Query Ops</span>
            <span className="admin-badge">Admin</span>
          </div>
        </div>
        <div className="admin-topbar-right">
          <span className="admin-user-name">{user?.username}</span>
          <button className="admin-logout" onClick={onLogout}>
            <LogOut size={14} />
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="admin-tabs">
        <button
          className={`admin-tab ${tab === "overview" ? "active" : ""}`}
          onClick={() => setTab("overview")}
        >
          <TrendingUp size={14} /> Overview
        </button>
        <button
          className={`admin-tab ${tab === "users" ? "active" : ""}`}
          onClick={() => setTab("users")}
        >
          <Users size={14} /> Users
        </button>
        <button
          className={`admin-tab ${tab === "transactions" ? "active" : ""}`}
          onClick={() => setTab("transactions")}
        >
          <CreditCard size={14} /> Transactions
        </button>
      </div>

      <div className="admin-content">
        {/* Success/error message */}
        {allocateMsg && (
          <div className="admin-toast">
            <CheckCircle2 size={14} /> {allocateMsg}
          </div>
        )}

        {/* Overview */}
        {tab === "overview" && stats && (
          <div className="admin-overview">
            <div className="admin-stat-grid">
              <div className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-blue">
                  <Users size={20} />
                </div>
                <div className="admin-stat-info">
                  <span className="admin-stat-num">{stats.total_users}</span>
                  <span className="admin-stat-label">Total Users</span>
                </div>
              </div>
              <div className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-green">
                  <Crown size={20} />
                </div>
                <div className="admin-stat-info">
                  <span className="admin-stat-num">{stats.paid_users}</span>
                  <span className="admin-stat-label">Paid Users</span>
                </div>
              </div>
              <div className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-purple">
                  <CreditCard size={20} />
                </div>
                <div className="admin-stat-info">
                  <span className="admin-stat-num">{stats.total_transactions}</span>
                  <span className="admin-stat-label">Transactions</span>
                </div>
              </div>
              <div className="admin-stat-card">
                <div className="admin-stat-icon admin-stat-orange">
                  <DollarSign size={20} />
                </div>
                <div className="admin-stat-info">
                  <span className="admin-stat-num">${stats.total_revenue}</span>
                  <span className="admin-stat-label">Total Revenue</span>
                </div>
              </div>
            </div>

            {/* Recent transactions */}
            <div className="admin-section">
              <h3>Recent Transactions</h3>
              {transactions.length === 0 ? (
                <div className="admin-empty">No transactions yet</div>
              ) : (
                <table className="admin-table">
                  <thead>
                    <tr>
                      <th>User</th>
                      <th>Amount</th>
                      <th>Card</th>
                      <th>Credits</th>
                      <th>Status</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.slice(0, 5).map((t) => (
                      <tr key={t.id}>
                        <td>
                          <div className="admin-user-cell">
                            <span className="admin-cell-name">{t.username}</span>
                            <span className="admin-cell-email">{t.email}</span>
                          </div>
                        </td>
                        <td>${t.amount}</td>
                        <td>{t.card_brand} ****{t.card_last4}</td>
                        <td>+{t.credits_added}</td>
                        <td>
                          <span className={`admin-status admin-status-${t.status}`}>
                            {t.status}
                          </span>
                        </td>
                        <td>{new Date(t.created_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        )}

        {/* Users tab */}
        {tab === "users" && (
          <div className="admin-users">
            <div className="admin-toolbar">
              <div className="admin-search">
                <Search size={14} />
                <input
                  type="text"
                  placeholder="Search users..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>

            <table className="admin-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Credits</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <div className="admin-user-cell">
                        <div className="admin-user-avatar">
                          {u.username?.[0]?.toUpperCase() || "U"}
                        </div>
                        <div>
                          <span className="admin-cell-name">{u.username}</span>
                          <span className="admin-cell-email">{u.email}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="admin-credits-badge">
                        {u.credits} credits
                      </span>
                    </td>
                    <td>
                      {u.has_paid ? (
                        <span className="admin-status admin-status-completed">Pro</span>
                      ) : (
                        <span className="admin-status admin-status-free">Free</span>
                      )}
                      {u.is_admin && (
                        <span className="admin-status admin-status-admin">Admin</span>
                      )}
                    </td>
                    <td>{new Date(u.created_at).toLocaleDateString()}</td>
                    <td>
                      {allocatingUser === u.id ? (
                        <div className="admin-allocate-inline">
                          <input
                            type="number"
                            value={allocateAmount}
                            onChange={(e) => setAllocateAmount(e.target.value)}
                            placeholder="Credits"
                            min="1"
                            className="admin-allocate-input"
                          />
                          <button className="admin-allocate-confirm" onClick={handleAllocate}>
                            <CheckCircle2 size={12} />
                          </button>
                          <button
                            className="admin-allocate-cancel"
                            onClick={() => { setAllocatingUser(null); setAllocateAmount(""); }}
                          >
                            <AlertCircle size={12} />
                          </button>
                        </div>
                      ) : (
                        <button
                          className="admin-action-btn"
                          onClick={() => setAllocatingUser(u.id)}
                          title="Add credits"
                        >
                          <Plus size={12} /> Credits
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Transactions tab */}
        {tab === "transactions" && (
          <div className="admin-transactions">
            <div className="admin-toolbar">
              <div className="admin-search">
                <Search size={14} />
                <input
                  type="text"
                  placeholder="Search transactions..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>

            {filteredTxns.length === 0 ? (
              <div className="admin-empty">No transactions found</div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Transaction ID</th>
                    <th>User</th>
                    <th>Amount</th>
                    <th>Card</th>
                    <th>Credits</th>
                    <th>Status</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTxns.map((t) => (
                    <tr key={t.id}>
                      <td className="admin-txn-id">{t.id.slice(0, 8)}...</td>
                      <td>
                        <div className="admin-user-cell">
                          <span className="admin-cell-name">{t.username}</span>
                          <span className="admin-cell-email">{t.email}</span>
                        </div>
                      </td>
                      <td className="admin-amount">${t.amount}</td>
                      <td>{t.card_brand} ****{t.card_last4}</td>
                      <td>+{t.credits_added}</td>
                      <td>
                        <span className={`admin-status admin-status-${t.status}`}>
                          {t.status}
                        </span>
                      </td>
                      <td>{new Date(t.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
