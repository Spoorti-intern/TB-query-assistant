
import axios from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_URL ||
  (window.location.hostname !== "localhost"
    ? "https://tb-query-assistant-tydh-iota.vercel.app"
    : "http://127.0.0.1:8103");

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Attach JWT token to every request if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("qops_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ==============================
// AUTH APIs
// ==============================

export const registerUser = async ({ email, username, password }) => {
  const response = await api.post("/api/auth/register", { email, username, password });
  return response.data;
};

export const loginUser = async ({ email, password }) => {
  const response = await api.post("/api/auth/login", { email, password });
  return response.data;
};

export const sendOTP = async ({ email, username, password }) => {
  const response = await api.post("/api/auth/send-otp", { email, username, password });
  return response.data;
};

export const verifyOTP = async ({ email, username, password, otp }) => {
  const response = await api.post("/api/auth/verify-otp", { email, username, password, otp });
  return response.data;
};

export const sendLoginOTP = async ({ email, password }) => {
  const response = await api.post("/api/auth/send-login-otp", { email, password });
  return response.data;
};

export const verifyLoginOTP = async ({ email, password, otp }) => {
  const response = await api.post("/api/auth/verify-login-otp", { email, password, otp });
  return response.data;
};

export const getMe = async () => {
  const response = await api.get("/api/auth/me");
  return response.data;
};

// ==============================
// PAYMENT APIs
// ==============================

export const processPayment = async (paymentData) => {
  const response = await api.post("/api/payments/process", paymentData);
  return response.data;
};

export const getPaymentHistory = async () => {
  const response = await api.get("/api/payments/history");
  return response.data;
};

export const getCredits = async () => {
  const response = await api.get("/api/payments/credits");
  return response.data;
};

export const useCredit = async () => {
  const response = await api.post("/api/payments/use-credit");
  return response.data;
};

// ==============================
// ADMIN APIs
// ==============================

export const getAdminUsers = async () => {
  const response = await api.get("/api/admin/users");
  return response.data;
};

export const getAdminTransactions = async () => {
  const response = await api.get("/api/admin/transactions");
  return response.data;
};

export const getAdminStats = async () => {
  const response = await api.get("/api/admin/stats");
  return response.data;
};

export const allocateCredits = async (userId, credits) => {
  const response = await api.post("/api/admin/allocate-credits", {
    user_id: userId,
    credits,
  });
  return response.data;
};

// ==============================
// CONNECTOR APIs
// ==============================

// Get all connectors
export const getConnectors = async () => {
  const response = await api.get("/api/connectors/");
  return response.data;
};

// Create a connector
export const createConnector = async (connectorData) => {
  const response = await api.post("/api/connectors/", connectorData);
  return response.data;
};

// Test database connection
export const testConnector = async (connectorId) => {
  const response = await api.post(
    `/api/connectors/${connectorId}/test`
  );
  return response.data;
};

// Discover database schema
export const getConnectorSchema = async (connectorId) => {
  const response = await api.get(
    `/api/connectors/${connectorId}/schema`
  );
  return response.data;
};

// Delete a connector
export const deleteConnector = async (connectorId) => {
  const response = await api.delete(
    `/api/connectors/${connectorId}`
  );
  return response.data;
};


// ==============================
// SQL QUERY APIs
// PostgreSQL, MySQL and Supabase
// ==============================

// Ask database questions using AI
export const askDatabase = async (connectorId, question) => {
  const response = await api.post(
    `/api/query/ask/${connectorId}`,
    { question }
  );

  return response.data;
};

// Execute manually supplied SQL
export const executeQuery = async (connectorId, sql) => {
  const response = await api.post(
    `/api/query/${connectorId}`,
    { sql }
  );

  return response.data;
};


// ==============================
// MONGODB QUERY APIs
// ==============================

// Ask MongoDB questions using AI (natural language)
export const askMongoDatabase = async (connectorId, question) => {
  const response = await api.post(
    `/api/mongodb/ask/${connectorId}`,
    { question }
  );

  return response.data;
};

// Execute a manual MongoDB query
export const executeMongoDBQuery = async (
  connectorId,
  queryData
) => {
  const response = await api.post(
    `/api/mongodb/${connectorId}/query`,
    queryData
  );

  return response.data;
};


// ==============================
// SMART CHAT API (legacy)
// ==============================

export const smartChat = async (message, connectorId = null) => {
  const response = await api.post("/api/chat/", {
    message,
    connector_id: connectorId,
  }, { timeout: 60000 });
  return response.data;
};


// ==============================
// AGENT STREAMING API
// ==============================

/**
 * Stream a chat message through the AI agent.
 * The agent decides what to do (connect, query, schema, general chat)
 * and streams SSE events back.
 *
 * @param {string}       message      - User message
 * @param {string|null}  connectorId  - Active connector ID (or null)
 * @param {Array}        history      - Recent chat history [{role, content}]
 * @param {Function}     onEvent      - Callback for each SSE event
 */
export async function streamAgentChat(message, connectorId, history, onEvent) {
  // AbortController with 90s timeout — prevents hanging forever
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  let response;
  try {
    const token = localStorage.getItem("qops_token");
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    response = await fetch(`${API_BASE_URL}/api/agent/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        message,
        connector_id: connectorId || null,
        history: history || [],
      }),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      throw new Error("Request timed out. The server took too long to respond.");
    }
    throw new Error("Could not connect to the server. Make sure the backend is running.");
  }

  if (!response.ok) {
    clearTimeout(timeoutId);
    const text = await response.text().catch(() => "");
    throw new Error(text || `Server error (HTTP ${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Reset timeout on each chunk — connection is alive
      clearTimeout(timeoutId);

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep incomplete line

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            // Skip heartbeat events — they're just keepalives
            if (data.type === "heartbeat") continue;
            onEvent(data);
          } catch {
            // skip malformed
          }
        }
      }
    }
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      throw new Error("Request timed out. The server took too long to respond.");
    }
    throw new Error("Connection lost while streaming response.");
  } finally {
    clearTimeout(timeoutId);
  }

  // flush remaining buffer
  if (buffer.startsWith("data: ")) {
    try {
      const data = JSON.parse(buffer.slice(6));
      if (data.type !== "heartbeat") onEvent(data);
    } catch {
      // ignore
    }
  }
}


// ==============================
// CHAT SESSION APIs
// ==============================

export const getSessions = async () => {
  const response = await api.get("/api/sessions/");
  return response.data;
};

export const createSession = async (data) => {
  const response = await api.post("/api/sessions/", data);
  return response.data;
};

export const getSession = async (sessionId) => {
  const response = await api.get(`/api/sessions/${sessionId}`);
  return response.data;
};

export const updateSession = async (sessionId, data) => {
  const response = await api.put(`/api/sessions/${sessionId}`, data);
  return response.data;
};

export const deleteSession = async (sessionId) => {
  const response = await api.delete(`/api/sessions/${sessionId}`);
  return response.data;
};

export const generateSessionTitle = async (sessionId, messages) => {
  const response = await api.post(`/api/sessions/${sessionId}/generate-title`, { messages });
  return response.data;
};


// ==============================
// EXPORT API INSTANCE
// ==============================

export default api;