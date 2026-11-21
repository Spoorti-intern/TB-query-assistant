import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";

/**
 * Custom code block with copy button and CSS-based SQL syntax highlighting.
 * Used as a custom renderer for ReactMarkdown's `code` element.
 */

// SQL keywords to highlight
const SQL_KEYWORDS = new Set([
  "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP",
  "ALTER", "TABLE", "INDEX", "VIEW", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER",
  "CROSS", "ON", "AND", "OR", "NOT", "IN", "EXISTS", "BETWEEN", "LIKE", "IS",
  "NULL", "AS", "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "UNION",
  "ALL", "DISTINCT", "TOP", "INTO", "VALUES", "SET", "CASE", "WHEN", "THEN",
  "ELSE", "END", "ASC", "DESC", "COUNT", "SUM", "AVG", "MIN", "MAX", "CAST",
  "COALESCE", "IFNULL", "ISNULL", "WITH", "RECURSIVE", "OVER", "PARTITION",
  "ROW_NUMBER", "RANK", "DENSE_RANK", "EXTRACT", "YEAR", "MONTH", "DAY",
  "DATE", "TIMESTAMP", "INTERVAL", "BOOLEAN", "INTEGER", "VARCHAR", "TEXT",
  "FLOAT", "DECIMAL", "PRIMARY", "KEY", "FOREIGN", "REFERENCES", "CONSTRAINT",
  "DEFAULT", "CHECK", "UNIQUE", "CASCADE", "RESTRICT", "TRUNCATE", "EXPLAIN",
  "ANALYZE", "BEGIN", "COMMIT", "ROLLBACK", "TRANSACTION", "GRANT", "REVOKE",
  "SCHEMA", "DATABASE", "USE", "SHOW", "DESCRIBE", "INFORMATION_SCHEMA",
  "SHOWPLAN_TEXT", "NOCOUNT",
]);

const SQL_FUNCTIONS = new Set([
  "COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "IFNULL", "ISNULL",
  "CAST", "CONVERT", "SUBSTRING", "TRIM", "UPPER", "LOWER", "LENGTH",
  "CONCAT", "REPLACE", "ROUND", "FLOOR", "CEIL", "ABS", "NOW", "CURRENT_TIMESTAMP",
  "DATEADD", "DATEDIFF", "GETDATE", "ROW_NUMBER", "RANK", "DENSE_RANK",
  "EXTRACT", "STRING_AGG", "GROUP_CONCAT", "ARRAY_AGG",
]);

function highlightSQL(code) {
  // Tokenize and highlight SQL
  const tokens = [];
  let i = 0;

  while (i < code.length) {
    // String literals (single quotes)
    if (code[i] === "'") {
      let end = i + 1;
      while (end < code.length && code[end] !== "'") end++;
      tokens.push({ type: "string", value: code.slice(i, end + 1) });
      i = end + 1;
      continue;
    }

    // Comments (-- single line)
    if (code[i] === "-" && code[i + 1] === "-") {
      let end = code.indexOf("\n", i);
      if (end === -1) end = code.length;
      tokens.push({ type: "comment", value: code.slice(i, end) });
      i = end;
      continue;
    }

    // Numbers
    if (/\d/.test(code[i]) && (i === 0 || /[\s,=(]/.test(code[i - 1]))) {
      let end = i;
      while (end < code.length && /[\d.]/.test(code[end])) end++;
      tokens.push({ type: "number", value: code.slice(i, end) });
      i = end;
      continue;
    }

    // Words (keywords, functions, identifiers)
    if (/[a-zA-Z_]/.test(code[i])) {
      let end = i;
      while (end < code.length && /[a-zA-Z0-9_]/.test(code[end])) end++;
      const word = code.slice(i, end);
      const upper = word.toUpperCase();
      if (SQL_FUNCTIONS.has(upper)) {
        tokens.push({ type: "function", value: word });
      } else if (SQL_KEYWORDS.has(upper)) {
        tokens.push({ type: "keyword", value: word });
      } else {
        tokens.push({ type: "identifier", value: word });
      }
      i = end;
      continue;
    }

    // Brackets [TableName]
    if (code[i] === "[") {
      let end = code.indexOf("]", i);
      if (end === -1) end = code.length - 1;
      tokens.push({ type: "identifier", value: code.slice(i, end + 1) });
      i = end + 1;
      continue;
    }

    // Operators and punctuation
    tokens.push({ type: "plain", value: code[i] });
    i++;
  }

  return tokens.map((t, idx) => {
    switch (t.type) {
      case "keyword":
        return <span key={idx} className="sql-keyword">{t.value}</span>;
      case "function":
        return <span key={idx} className="sql-function">{t.value}</span>;
      case "string":
        return <span key={idx} className="sql-string">{t.value}</span>;
      case "number":
        return <span key={idx} className="sql-number">{t.value}</span>;
      case "comment":
        return <span key={idx} className="sql-comment">{t.value}</span>;
      case "identifier":
        return <span key={idx} className="sql-identifier">{t.value}</span>;
      default:
        return <span key={idx}>{t.value}</span>;
    }
  });
}

export default function CodeBlock({ children, className, ...props }) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const language = match ? match[1] : "";
  const isBlock = className || (typeof children === "string" && children.includes("\n"));
  const code = String(children).replace(/\n$/, "");

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  // Inline code (no language, single line)
  if (!isBlock) {
    return <code className={className} {...props}>{children}</code>;
  }

  // Determine if SQL-like
  const isSql = language === "sql" || language === "mssql" || language === "mysql" ||
    language === "postgresql" || language === "tsql" || language === "" && /\b(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|FROM|WHERE)\b/i.test(code);

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span className="code-block-lang">{language || (isSql ? "SQL" : "code")}</span>
        <button
          className={`code-block-copy ${copied ? "copied" : ""}`}
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy code"}
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="code-block-pre">
        <code className={className}>
          {isSql ? highlightSQL(code) : children}
        </code>
      </pre>
    </div>
  );
}
