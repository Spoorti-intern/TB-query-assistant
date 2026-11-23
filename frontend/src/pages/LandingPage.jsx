import {
  Database,
  Zap,
  Shield,
  Globe,
  ArrowRight,
  MessageSquare,
  BarChart3,
  Lock,
  Terminal,
  Code2,
  Sparkles,
  ChevronRight,
} from "lucide-react";

export default function LandingPage({ onGetStarted }) {
  return (
    <div className="landing-page">
      {/* Nav */}
      <nav className="landing-nav">
        <div className="landing-nav-inner">
          <div className="landing-nav-brand">
            <div className="landing-nav-logo">
              <Database size={18} />
            </div>
            <span className="landing-nav-name">Query Ops</span>
          </div>
          <button className="landing-nav-cta" onClick={onGetStarted}>
            Get Started <ArrowRight size={14} />
          </button>
        </div>
      </nav>

      {/* Hero */}
      <section className="landing-hero">
        <div className="landing-hero-bg">
          <div className="landing-hero-grid" />
          <div className="landing-hero-glow" />
        </div>

        <div className="landing-hero-inner">
          <div className="landing-hero-badge">
            <Sparkles size={12} />
            AI-Powered Database Assistant
          </div>
          <h1 className="landing-hero-title">
            Query your databases
            <br />
            with <span className="landing-gradient-text">natural language</span>
          </h1>
          <p className="landing-hero-desc">
            Connect any database, ask questions in plain English, and get instant
            SQL results. No more writing complex queries from scratch.
          </p>
          <div className="landing-hero-actions">
            <button className="landing-btn-primary" onClick={onGetStarted}>
              Get Started <ArrowRight size={16} />
            </button>
            <a href="#how-it-works" className="landing-btn-ghost">
              See how it works <ChevronRight size={14} />
            </a>
          </div>

          {/* Terminal preview */}
          <div className="landing-terminal-preview">
            <div className="landing-terminal-bar">
              <div className="landing-terminal-dots">
                <span />
                <span />
                <span />
              </div>
              <span className="landing-terminal-title">Query Ops</span>
            </div>
            <div className="landing-terminal-body">
              <div className="landing-terminal-line">
                <span className="landing-t-prompt">{">"}</span>
                <span className="landing-t-input">
                  Show me top 10 customers by revenue this month
                </span>
              </div>
              <div className="landing-terminal-line landing-t-fade">
                <span className="landing-t-label">SQL</span>
                <span className="landing-t-sql">
                  SELECT name, SUM(amount) as revenue FROM orders ...
                </span>
              </div>
              <div className="landing-terminal-line landing-t-fade">
                <span className="landing-t-label landing-t-label-green">
                  Result
                </span>
                <span className="landing-t-result">
                  10 rows returned in 42ms
                </span>
              </div>
            </div>
          </div>

          {/* DB types */}
          <div className="landing-db-strip">
            {[
              "PostgreSQL",
              "MySQL",
              "MongoDB",
              "SQL Server",
              "Redis",
              "Oracle",
              "Supabase",
              "SQLite",
              "Neo4j",
              "ClickHouse",
            ].map((db) => (
              <span key={db} className="landing-db-chip">
                {db}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="landing-features">
        <div className="landing-features-inner">
          <h2 className="landing-section-title">
            Everything you need to query smarter
          </h2>
          <div className="landing-features-grid">
            <div className="landing-feature-card">
              <div className="landing-feature-icon">
                <MessageSquare size={22} />
              </div>
              <h3>Natural Language Queries</h3>
              <p>
                Ask questions in plain English. Our AI converts them to optimized
                SQL queries automatically.
              </p>
            </div>
            <div className="landing-feature-card">
              <div className="landing-feature-icon landing-feature-icon-purple">
                <Globe size={22} />
              </div>
              <h3>16+ Database Types</h3>
              <p>
                Connect to PostgreSQL, MySQL, MongoDB, Redis, Neo4j,
                Elasticsearch, and many more.
              </p>
            </div>
            <div className="landing-feature-card">
              <div className="landing-feature-icon landing-feature-icon-green">
                <Shield size={22} />
              </div>
              <h3>Read-Only & Secure</h3>
              <p>
                All queries are validated as read-only. Your data is safe with
                encrypted credentials.
              </p>
            </div>
            <div className="landing-feature-card">
              <div className="landing-feature-icon landing-feature-icon-orange">
                <BarChart3 size={22} />
              </div>
              <h3>Instant Results</h3>
              <p>
                Get formatted results with AI explanations. Understand your data
                at a glance.
              </p>
            </div>
            <div className="landing-feature-card">
              <div className="landing-feature-icon landing-feature-icon-cyan">
                <Zap size={22} />
              </div>
              <h3>Query Optimization</h3>
              <p>
                Get execution plans, index suggestions, and performance insights
                for slow queries.
              </p>
            </div>
            <div className="landing-feature-card">
              <div className="landing-feature-icon landing-feature-icon-red">
                <Lock size={22} />
              </div>
              <h3>Secure Authentication</h3>
              <p>
                Your account and database credentials are protected with
                industry-standard encryption.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="landing-steps" id="how-it-works">
        <div className="landing-steps-inner">
          <h2 className="landing-section-title">How it works</h2>
          <div className="landing-steps-grid">
            <div className="landing-step">
              <div className="landing-step-num">
                <Terminal size={20} />
              </div>
              <h3>Connect</h3>
              <p>
                Paste your database connection string or fill in the details. We
                support 16+ database types.
              </p>
            </div>
            <div className="landing-step-connector">
              <ChevronRight size={20} />
            </div>
            <div className="landing-step">
              <div className="landing-step-num landing-step-num-purple">
                <Code2 size={20} />
              </div>
              <h3>Ask</h3>
              <p>
                Type your question in plain English. &ldquo;Show me the top 10
                customers by revenue.&rdquo;
              </p>
            </div>
            <div className="landing-step-connector">
              <ChevronRight size={20} />
            </div>
            <div className="landing-step">
              <div className="landing-step-num landing-step-num-green">
                <BarChart3 size={20} />
              </div>
              <h3>Get Results</h3>
              <p>
                See the generated SQL, formatted results, and an AI-powered
                explanation of your data.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="landing-cta">
        <div className="landing-cta-inner">
          <div className="landing-cta-glow" />
          <h2>Ready to query smarter?</h2>
          <p>
            Start using Query Ops today. Connect your database in seconds.
          </p>
          <button
            className="landing-btn-primary landing-btn-lg"
            onClick={onGetStarted}
          >
            Get Started Free <ArrowRight size={16} />
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="landing-footer-brand">
            <Database size={16} />
            <span>Query Ops</span>
          </div>
          <span className="landing-footer-copy">
            &copy; {new Date().getFullYear()} Query Ops. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  );
}
