import { useMemo } from "react";
import { Database, Search, Zap, Table2, BarChart3 } from "lucide-react";

export default function EmptyState({ onSuggestion, tableNames = [] }) {
  // Pick random sample tables for suggestions
  const sampleTables = useMemo(() => {
    if (!tableNames.length) return [];
    const shuffled = [...tableNames].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, 3);
  }, [tableNames]);

  // Dynamic cards based on actual table names — ALL database-related
  const cards = useMemo(() => {
    if (sampleTables.length >= 2) {
      return [
        {
          icon: <Table2 size={18} />,
          title: "Query",
          desc: `Fetch data from ${sampleTables[0]}`,
          prompt: `Show me the first 10 rows from ${sampleTables[0]}`,
        },
        {
          icon: <Search size={18} />,
          title: "Explore",
          desc: "Discover all tables and columns",
          prompt: "What tables are in this database?",
        },
        {
          icon: <BarChart3 size={18} />,
          title: "Analyze",
          desc: `Count rows in ${sampleTables[1]}`,
          prompt: `How many rows are in ${sampleTables[1]}?`,
        },
        {
          icon: <Zap size={18} />,
          title: "Optimize",
          desc: "Analyze and speed up slow queries",
          prompt: "Suggest optimizations for my most complex query",
        },
      ];
    }

    // Fallback: no connector or no tables yet
    return [
      {
        icon: <Database size={18} />,
        title: "Query",
        desc: "Tables, columns, SQL, or plain English",
        prompt: "Show me the top 10 customers by revenue",
      },
      {
        icon: <Search size={18} />,
        title: "Explore",
        desc: "Discover schemas across any database",
        prompt: "What tables are in this database?",
      },
      {
        icon: <BarChart3 size={18} />,
        title: "Analyze",
        desc: "Aggregate, count, and summarize data",
        prompt: "How many records are in each table?",
      },
      {
        icon: <Zap size={18} />,
        title: "Optimize",
        desc: "Analyze and speed up slow queries",
        prompt: "Why is this query slow?",
      },
    ];
  }, [sampleTables]);

  return (
    <div className="empty-state">
      <div className="empty-logo">
        <Database size={26} />
      </div>
      <h1 className="empty-title">TB Query Assistant</h1>
      <p className="empty-subtitle">
        Ask me about your database — queries, tables, columns, rows, schema, or any data question.
      </p>

      <div className="empty-cards">
        {cards.map((card) => (
          <button
            key={card.title}
            className="empty-card"
            onClick={() => onSuggestion(card.prompt)}
          >
            <div className="empty-card-icon">{card.icon}</div>
            <div className="empty-card-text">
              <strong>{card.title}</strong>
              <span>{card.desc}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
