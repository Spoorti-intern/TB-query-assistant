import { useState, useRef, useEffect } from "react";
import {
  Database,
  Mail,
  Lock,
  User,
  Eye,
  EyeOff,
  ArrowRight,
  ArrowLeft,
  Loader,
  AlertCircle,
  WifiOff,
  Terminal,
  Table2,
  Braces,
  CheckCircle2,
  KeyRound,
} from "lucide-react";
import { loginUser, sendOTP, verifyOTP } from "../api";

export default function LoginPage({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [errorType, setErrorType] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  // OTP state (registration only)
  const [otpStep, setOtpStep] = useState(false);
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [otpSent, setOtpSent] = useState(false);
  const [resendTimer, setResendTimer] = useState(0);
  const otpRefs = useRef([]);

  // Resend timer countdown
  useEffect(() => {
    if (resendTimer <= 0) return;
    const t = setTimeout(() => setResendTimer((v) => v - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  const handleOtpChange = (index, value) => {
    if (value.length > 1) value = value.slice(-1);
    if (value && !/^\d$/.test(value)) return;

    const newOtp = [...otp];
    newOtp[index] = value;
    setOtp(newOtp);

    if (value && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (index, e) => {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  const handleOtpPaste = (e) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 6) {
      setOtp(pasted.split(""));
      otpRefs.current[5]?.focus();
      e.preventDefault();
    }
  };

  // ============ REGISTRATION OTP ============

  const handleSendRegisterOtp = async () => {
    setError("");
    setErrorType("");

    if (!email.trim()) {
      setError("Please enter your email address");
      setErrorType("validation");
      return;
    }
    if (!username.trim() || username.trim().length < 3) {
      setError("Username must be at least 3 characters");
      setErrorType("validation");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters");
      setErrorType("validation");
      return;
    }

    setLoading(true);
    try {
      await sendOTP({ email, username, password });
      setOtpStep(true);
      setOtpSent(true);
      setResendTimer(60);
      setError("");
      setSuccessMessage("OTP sent to your email! Check your inbox.");
      setTimeout(() => setSuccessMessage(""), 4000);
    } catch (err) {
      if (!err.response) {
        setErrorType("network");
        setError("Cannot connect to the server. Please check if the backend is running.");
      } else {
        setErrorType("auth");
        setError(err.response?.data?.detail || "Failed to send OTP. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyRegisterOtp = async () => {
    const otpCode = otp.join("");
    if (otpCode.length !== 6) {
      setError("Please enter the complete 6-digit code");
      setErrorType("validation");
      return;
    }

    setError("");
    setLoading(true);
    try {
      await verifyOTP({ email, username, password, otp: otpCode });
      // Registration successful — switch to login with email pre-filled
      const registeredEmail = email;
      setOtpStep(false);
      setIsRegister(false);
      setOtp(["", "", "", "", "", ""]);
      setPassword("");
      setUsername("");
      setEmail(registeredEmail); // Auto-fill email in login form
      setSuccessMessage("Account created! Sign in with your credentials.");
    } catch (err) {
      if (!err.response) {
        setErrorType("network");
        setError("Cannot connect to the server.");
      } else {
        setErrorType("auth");
        setError(err.response?.data?.detail || "Invalid OTP. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  // ============ VERIFY & RESEND (registration only) ============

  const handleVerifyOtp = () => {
    handleVerifyRegisterOtp();
  };

  const handleResendOtp = async () => {
    if (resendTimer > 0) return;
    setError("");
    setLoading(true);
    try {
      await sendOTP({ email, username, password });
      setResendTimer(60);
      setOtp(["", "", "", "", "", ""]);
      setSuccessMessage("New OTP sent to your email!");
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      setErrorType("auth");
      setError(err.response?.data?.detail || "Failed to resend OTP.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setErrorType("");
    setSuccessMessage("");

    if (!email.trim()) {
      setError("Please enter your email address");
      setErrorType("validation");
      return;
    }

    if (isRegister) {
      handleSendRegisterOtp();
      return;
    }

    // Login — direct login, no OTP
    if (!password) {
      setError("Please enter your password");
      setErrorType("validation");
      return;
    }

    setLoading(true);
    try {
      const result = await loginUser({ email, password });
      onLogin(result);
    } catch (err) {
      if (!err.response) {
        setErrorType("network");
        setError("Cannot connect to the server. Please check if the backend is running.");
      } else if (err.response.status === 401) {
        setErrorType("auth");
        setError("Invalid email or password. Please try again.");
      } else {
        setErrorType("auth");
        setError(err.response?.data?.detail || "Login failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setIsRegister(!isRegister);
    setOtpStep(false);
    setOtp(["", "", "", "", "", ""]);
    setError("");
    setErrorType("");
    setSuccessMessage("");
  };

  const goBackFromOtp = () => {
    setOtpStep(false);
    setOtp(["", "", "", "", "", ""]);
    setError("");
  };

  return (
    <div className="login-page">
      {/* Background decorations */}
      <div className="login-bg-decor">
        <div className="login-bg-grid" />
        <div className="login-bg-glow login-bg-glow-1" />
        <div className="login-bg-glow login-bg-glow-2" />
        <div className="login-floating-icons">
          <div className="login-float-icon float-1"><Terminal size={20} /></div>
          <div className="login-float-icon float-2"><Table2 size={20} /></div>
          <div className="login-float-icon float-3"><Braces size={20} /></div>
          <div className="login-float-icon float-4"><Database size={18} /></div>
        </div>
      </div>

      <div className="login-card">
        {/* Logo + branding */}
        <div className="login-header">
          <div className="login-logo">
            <Database size={26} />
          </div>
          <h1 className="login-title">Query Ops</h1>
          <p className="login-subtitle">
            {otpStep
              ? "Enter the verification code sent to your email"
              : isRegister
                ? "Create your account to get started"
                : "Welcome back! Sign in to continue"}
          </p>
        </div>

        {/* OTP verification step (shared for both register & login) */}
        {otpStep ? (
          <div className="login-otp-section">
            {successMessage && (
              <div className="login-success">
                <div className="login-success-icon"><CheckCircle2 size={16} /></div>
                <span className="login-success-text">{successMessage}</span>
              </div>
            )}
            {error && (
              <div className={`login-error login-error-${errorType}`}>
                <div className="login-error-icon">
                  {errorType === "network" ? <WifiOff size={16} /> : <AlertCircle size={16} />}
                </div>
                <div className="login-error-content">
                  <span className="login-error-text">{error}</span>
                </div>
              </div>
            )}

            <div className="otp-email-display">
              <Mail size={16} />
              <span>{email}</span>
            </div>

            <div className="otp-input-group" onPaste={handleOtpPaste}>
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => (otpRefs.current[i] = el)}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOtpChange(i, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(i, e)}
                  className={`otp-input ${digit ? "otp-input-filled" : ""}`}
                  disabled={loading}
                  autoFocus={i === 0}
                  autoComplete="off"
                  name={`otp-${i}-${Date.now()}`}
                />
              ))}
            </div>

            <button
              className="login-submit"
              onClick={handleVerifyOtp}
              disabled={loading || otp.join("").length !== 6}
            >
              {loading ? (
                <>
                  <Loader size={18} className="spin" />
                  <span>Verifying...</span>
                </>
              ) : (
                <>
                  <KeyRound size={16} />
                  Verify & Create Account
                </>
              )}
            </button>

            <div className="otp-actions">
              <button className="otp-back-btn" onClick={goBackFromOtp} disabled={loading}>
                <ArrowLeft size={14} /> Back
              </button>
              <button
                className="otp-resend-btn"
                onClick={handleResendOtp}
                disabled={loading || resendTimer > 0}
              >
                {resendTimer > 0 ? `Resend in ${resendTimer}s` : "Resend Code"}
              </button>
            </div>
          </div>
        ) : (
          /* Regular login/register form */
          <form className="login-form" onSubmit={handleSubmit}>
            {successMessage && (
              <div className="login-success">
                <div className="login-success-icon"><CheckCircle2 size={16} /></div>
                <span className="login-success-text">{successMessage}</span>
              </div>
            )}

            {error && (
              <div className={`login-error login-error-${errorType}`}>
                <div className="login-error-icon">
                  {errorType === "network" ? <WifiOff size={16} /> : <AlertCircle size={16} />}
                </div>
                <div className="login-error-content">
                  <span className="login-error-text">{error}</span>
                  {errorType === "network" && (
                    <span className="login-error-hint">
                      Run: <code>uvicorn app.main:app --reload</code> in the backend directory
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Email */}
            <div className="login-field">
              <label htmlFor="email">Email</label>
              <div className="login-input-wrapper">
                <Mail size={16} className="login-input-icon" />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  autoComplete="email"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Username (register only) */}
            {isRegister && (
              <div className="login-field">
                <label htmlFor="username">Username</label>
                <div className="login-input-wrapper">
                  <User size={16} className="login-input-icon" />
                  <input
                    id="username"
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="Choose a username"
                    required
                    autoComplete="username"
                    disabled={loading}
                  />
                </div>
              </div>
            )}

            {/* Password */}
            <div className="login-field">
              <label htmlFor="password">Password</label>
              <div className="login-input-wrapper">
                <Lock size={16} className="login-input-icon" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={isRegister ? "Min. 6 characters" : "Enter your password"}
                  required
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  disabled={loading}
                />
                <button
                  type="button"
                  className="login-eye-btn"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button type="submit" className="login-submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader size={18} className="spin" />
                  <span>{isRegister ? "Sending OTP..." : "Verifying..."}</span>
                </>
              ) : (
                <>
                  {isRegister ? "Send Verification Code" : "Sign In"}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>
        )}

        {/* Switch mode */}
        {!otpStep && (
          <div className="login-switch">
            {isRegister ? (
              <span>
                Already have an account?{" "}
                <button onClick={switchMode}>Sign In</button>
              </span>
            ) : (
              <span>
                Don&apos;t have an account?{" "}
                <button onClick={switchMode}>Create Account</button>
              </span>
            )}
          </div>
        )}

        {/* DB badge strip */}
        <div className="login-db-badge">
          <span>PostgreSQL</span>
          <span className="login-db-dot" />
          <span>MySQL</span>
          <span className="login-db-dot" />
          <span>MongoDB</span>
          <span className="login-db-dot" />
          <span>Redis</span>
        </div>
      </div>
    </div>
  );
}
