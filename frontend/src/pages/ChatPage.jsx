import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Send, User, Loader, Plus, RefreshCw, CheckCircle2, AlertCircle, Brain, Database, Search, Zap, Link2, Shield, Paperclip, Image, FileText, Link, FileCode, ArrowRight, Crown, CreditCard } from "lucide-react";
import { streamAgentChat } from "../api";
import { toast } from "../components/Toast";
import EmptyState from "../components/EmptyState";
import CodeBlock from "../components/CodeBlock";

export default function ChatPage({
  connectors,
  selectedConnectorId,
  onSelectConnector,
  onConnectorAdded,
  messages,
  setMessages,
  onFirstMessage,
  tableNames = [],
  onDetectReason,
  credits = 0,
  hasPaid = false,
  onUseCredit,
  onUpgrade,
}) {
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const sendingRef = useRef(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const attachRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close attach menu on outside click
  useEffect(() => {
    if (!attachMenuOpen) return;
    const handleClick = (e) => {
      if (attachRef.current && !attachRef.current.contains(e.target)) {
        setAttachMenuOpen(false);
      }
    };
    const timer = setTimeout(() => {
      document.addEventListener("mousedown", handleClick);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", handleClick);
    };
  }, [attachMenuOpen]);

  const activeConnector = connectors.find((c) => String(c.id) === String(selectedConnectorId));

  const handleSend = async (text) => {
    text = (text || input).trim();
    if (!text || isStreaming || sendingRef.current) return;

    // Check credits before sending
    if (credits <= 0) {
      // Show payment wall
      if (onUpgrade) onUpgrade();
      return;
    }

    // Use a credit
    if (onUseCredit) {
      const allowed = await onUseCredit();
      if (!allowed) return;
    }

    sendingRef.current = true;

    setInput("");
    inputRef.current?.focus();

    if (messages.length === 0 && onFirstMessage) {
      onFirstMessage(text);
    }

    setMessages((prev) => [...prev, { role: "user", content: text }]);

    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: "",
        status: "thinking",
        statusMessages: [],
        steps: [],
        toolResults: [],
      },
    ]);

    setIsStreaming(true);

    const history = messages
      .filter((m) => m.status === "done" || m.role === "user")
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      await streamAgentChat(
        text,
        selectedConnectorId || null,
        history,
        (event) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = { ...updated[updated.length - 1] };

            switch (event.type) {
              case "status": {
                last.status = "tool_running";
                const steps = [...(last.steps || [])];
                const existingIdx = steps.findIndex(s => s.step === event.step);
                const stepData = {
                  step: event.step,
                  label: event.label || event.content || "Processing\u2026",
                  description: event.description || "",
                  phase: event.phase || "running",
                  tool: event.tool || "",
                };
                if (existingIdx >= 0) {
                  steps[existingIdx] = stepData;
                } else {
                  steps.push(stepData);
                }
                last.steps = steps;
                if (event.content && !event.step) {
                  last.statusMessages = [
                    ...(last.statusMessages || []),
                    event.content,
                  ];
                }
                break;
              }

              case "connector_detected":
                if (event.connector_id && onSelectConnector) {
                  onSelectConnector(event.connector_id);
                }
                if (event.reason && onDetectReason) {
                  onDetectReason(event.reason);
                }
                break;

              case "tool_result":
                last.toolResults = [
                  ...(last.toolResults || []),
                  event,
                ];
                if (
                  event.tool === "connect_database" &&
                  event.data?.success &&
                  onConnectorAdded
                ) {
                  onConnectorAdded();
                }
                break;

              case "content":
                if (last.status === "error") {
                  last.content = event.content;
                } else {
                  last.content = (last.content || "") + event.content;
                }
                last.status = "streaming";
                break;

              case "error":
                if (!last.content || last.status !== "streaming") {
                  last.status = "error";
                  last.content = event.content;
                }
                break;

              case "done":
                last.status = "done";
                break;

              default:
                break;
            }

            updated[updated.length - 1] = last;
            return updated;
          });
        }
      );
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          status: "error",
          content: `Connection error: ${err.message}`,
        };
        return updated;
      });
      toast.error("Failed to reach the server.");
    }

    setIsStreaming(false);
    sendingRef.current = false;
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleAttachFile = () => {
    setAttachMenuOpen(false);
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".sql,.csv,.json,.txt,.xlsx,.xls,.xml,.yaml,.yml";
    inp.onchange = (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = ev.target.result;
          setInput((prev) => (prev ? prev + "\n\n" : "") + `--- File: ${file.name} ---\n${content}`);
          inputRef.current?.focus();
          toast.info(`"${file.name}" attached \u2014 send to analyze.`);
        };
        reader.readAsText(file);
      }
    };
    inp.click();
  };

  const handleAttachEnvFile = () => {
    setAttachMenuOpen(false);
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".env,.env.local,.env.example,.env.production,.env.development,.ini,.conf,.cfg,.toml";
    inp.onchange = (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = ev.target.result;
          setInput((prev) => (prev ? prev + "\n\n" : "") + `--- Config: ${file.name} ---\n${content}`);
          inputRef.current?.focus();
          toast.info(`"${file.name}" attached \u2014 connection details will be extracted.`);
        };
        reader.readAsText(file);
      }
    };
    inp.click();
  };

  const handleAttachImage = () => {
    setAttachMenuOpen(false);
    const inp = document.createElement("input");
    inp.type = "file";
    inp.accept = "image/*";
    inp.onchange = (e) => {
      const file = e.target.files[0];
      if (file) {
        toast.info(`Image "${file.name}" selected \u2014 describe what you need.`);
      }
    };
    inp.click();
  };

  const handleAttachLink = () => {
    setAttachMenuOpen(false);
    const link = prompt("Paste a database URL, connection string, or any link:");
    if (link?.trim()) {
      const detectedType = detectDbTypeFromLink(link.trim());
      if (detectedType) {
        toast.info(`Detected ${detectedType.toUpperCase()} connection \u2014 send to connect.`);
      }
      setInput((prev) => (prev ? prev + "\n" : "") + link.trim());
      inputRef.current?.focus();
    }
  };

  function detectDbTypeFromLink(text) {
    const patterns = [
      { type: "PostgreSQL", re: /postgres(ql)?:\/\//i },
      { type: "MySQL", re: /mysql:\/\//i },
      { type: "MongoDB", re: /mongodb(\+srv)?:\/\//i },
      { type: "SQL Server", re: /mssql(\+pymssql|\+pyodbc)?:\/\//i },
      { type: "Redis", re: /rediss?:\/\//i },
      { type: "SQLite", re: /sqlite:\/\/\//i },
      { type: "Oracle", re: /oracle:\/\//i },
      { type: "MariaDB", re: /mariadb:\/\//i },
      { type: "CockroachDB", re: /cockroachdb:\/\//i },
      { type: "ClickHouse", re: /clickhouse:\/\//i },
      { type: "Neo4j", re: /bolt:\/\//i },
      { type: "Supabase", re: /supabase\.co/i },
      { type: "Neon", re: /neon\.tech/i },
    ];
    for (const p of patterns) {
      if (p.re.test(text)) return p.type;
    }
    return null;
  }

  const hasMessages = messages.length > 0;
  const noCredits = credits <= 0;

  return (
    <div className="chat-container">
      {hasMessages ? (
        <div className="chat-messages">
          <div className="chat-messages-inner">
            {messages.map((msg, i) => (
              <div key={i} className={`msg msg--${msg.role}`}>
                <div className="msg-avatar">
                  {msg.role === "user" ? <User size={14} /> : <Bot size={14} />}
                </div>
                <div className="msg-body">
                  {msg.steps?.length > 0 && (
                    <div className="msg-progress-block">
                      {(() => {
                        const collapsed = [];
                        for (const s of msg.steps) {
                          const last = collapsed[collapsed.length - 1];
                          if (last && last.label === s.label && last.tool === s.tool) {
                            last.count = (last.count || 1) + 1;
                            last.phase = s.phase;
                          } else {
                            collapsed.push({ ...s, count: 1 });
                          }
                        }
                        return collapsed.map((s, j) => {
                          const StepIcon = s.tool === "_thinking" ? Brain
                            : s.tool === "query_database" ? Database
                            : s.tool === "search_tables" ? Search
                            : s.tool === "discover_schema" ? Database
                            : s.tool === "connect_database" ? Link2
                            : Zap;
                          return (
                            <div key={j} className={`progress-step progress-step--${s.phase}`}>
                              <div className="progress-step-icon">
                                {s.phase === "running" ? (
                                  <Loader size={16} className="spin" />
                                ) : s.phase === "done" ? (
                                  <CheckCircle2 size={16} />
                                ) : (
                                  <AlertCircle size={16} />
                                )}
                              </div>
                              <div className="progress-step-content">
                                <div className="progress-step-label">
                                  <StepIcon size={13} />
                                  {s.label}{s.count > 1 ? ` (${s.count} queries)` : ""}
                                </div>
                                {s.description && (
                                  <div className="progress-step-desc">{s.description}</div>
                                )}
                              </div>
                            </div>
                          );
                        });
                      })()}
                    </div>
                  )}

                  {msg.status === "thinking" && (
                    <div className="msg-thinking">
                      <span className="msg-thinking-dot" />
                      <span className="msg-thinking-dot" />
                      <span className="msg-thinking-dot" />
                    </div>
                  )}

                  {msg.content && (
                    <div className="msg-bubble">
                      {msg.role === "user" ? (
                        msg.content
                      ) : (
                        <div className="md">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              code({ children, className, node, ...rest }) {
                                return <CodeBlock className={className} {...rest}>{children}</CodeBlock>;
                              },
                              pre({ children }) {
                                return <>{children}</>;
                              },
                            }}
                          >
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      )}
                    </div>
                  )}

                  {msg.status === "streaming" && (
                    <span className="msg-cursor">|</span>
                  )}

                  {msg.status === "error" && msg.role === "assistant" && (
                    <button
                      className="msg-retry-btn"
                      onClick={() => {
                        const userMsg = messages.slice(0, i).reverse().find(m => m.role === "user");
                        if (userMsg) {
                          setMessages(prev => prev.filter((_, idx) => idx !== i));
                          setTimeout(() => handleSend(userMsg.content), 100);
                        }
                      }}
                    >
                      <RefreshCw size={12} /> Retry
                    </button>
                  )}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        </div>
      ) : (
        <EmptyState onSuggestion={(prompt) => handleSend(prompt)} tableNames={tableNames} />
      )}

      <div className="composer-wrapper">
        {/* No credits — show upgrade CTA */}
        {noCredits ? (
          <div className="credits-composer-cta">
            <div className="credits-cta-icon">
              <Crown size={20} />
            </div>
            <p>You&apos;ve used all your credits. Purchase more to continue querying your databases.</p>
            <button onClick={onUpgrade}>
              <CreditCard size={14} /> Buy Credits <ArrowRight size={14} />
            </button>
          </div>
        ) : (
          <>
            <div className="composer">
              {/* Attach menu */}
              <div className="attach-menu-wrapper" ref={attachRef}>
                <button
                  className="composer-btn"
                  onClick={() => setAttachMenuOpen(!attachMenuOpen)}
                  title="Attach file, image, or link"
                >
                  <Plus size={18} />
                </button>

                {attachMenuOpen && (
                  <div className="attach-menu">
                    <button className="attach-menu-item" onClick={handleAttachFile}>
                      <FileText size={14} />
                      <span>Query / Data File</span>
                      <span className="attach-menu-hint">.sql, .csv, .json</span>
                    </button>
                    <button className="attach-menu-item" onClick={handleAttachEnvFile}>
                      <FileCode size={14} />
                      <span>Config / .env File</span>
                      <span className="attach-menu-hint">.env, .ini, .toml</span>
                    </button>
                    <button className="attach-menu-item" onClick={handleAttachImage}>
                      <Image size={14} />
                      <span>Image / Screenshot</span>
                      <span className="attach-menu-hint">Schema diagram, ERD</span>
                    </button>
                    <button className="attach-menu-item" onClick={handleAttachLink}>
                      <Link size={14} />
                      <span>Paste Link / URL</span>
                      <span className="attach-menu-hint">DB URL, connection string</span>
                    </button>
                  </div>
                )}
              </div>

              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your database \u2014 tables, queries, columns, rows..."
                disabled={isStreaming}
                rows={1}
              />
              <div className="composer-actions">
                <button
                  className="composer-send"
                  onClick={() => handleSend()}
                  disabled={isStreaming || !input.trim()}
                >
                  {isStreaming ? (
                    <Loader size={16} className="spin" />
                  ) : (
                    <Send size={16} />
                  )}
                </button>
              </div>
            </div>
            <div className="composer-footer">
              <span className="composer-footer-credits">
                <CreditCard size={10} />
                {credits} {credits === 1 ? "credit" : "credits"} remaining
              </span>
              <span className="composer-footer-ro">
                <Shield size={10} />
                Read-only queries
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
