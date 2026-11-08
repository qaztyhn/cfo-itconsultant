/**
 * 5.0 Sign in — POST /auth/login; thẻ tài khoản demo gồm Customer service, Business owner (03 #24).
 * Chuyển hướng sau đăng nhập do GuestOnly (app/guards.tsx) đảm nhiệm: setAuth đổi store → quay lại trang đang vào dở
 * nếu được phép, không thì màn mặc định theo vai trò. Thẻ demo chỉ điền email; KHÔNG hard-code mật khẩu (09 bất biến 25).
 * Owner: Dev 3 (luồng C) — M0.
 */
import { useRef, useState, type FormEvent } from "react";
import { login } from "../../api/auth";
import { isApiError } from "../../api/client";
import { APP_ENV, isDemoEnv } from "../../api/config";
import { useAuthStore } from "../../app/store";
import { DemoBanner } from "../../components/DemoBanner";

const DEMO_ACCOUNTS = [
  { email: "dispatcher@cfo.demo", title: "Dispatcher", hint: "Plans & approvals" },
  { email: "sales@cfo.demo", title: "Sales", hint: "Order intake" },
  { email: "wm.got@cfo.demo", title: "Warehouse manager", hint: "Prep & milestones" },
  { email: "driver1@cfo.demo", title: "Driver", hint: "PWA on phone" },
  { email: "admin@cfo.demo", title: "Admin", hint: "Data & inbox" },
  { email: "cs@cfo.demo", title: "Customer service", hint: "Status & contact log" },
  { email: "owner@cfo.demo", title: "Business owner", hint: "KPIs, read-only" },
] as const;

/** Ba trụ cột ở nửa trái (03 mục 5.0). Dùng <div>, không dùng <li>, để không lẫn với danh sách thẻ demo. */
const PILLARS = [
  { no: "01", title: "Time-phased inventory" },
  { no: "02", title: "Warehouse readiness" },
  { no: "03", title: "Fleet & delivery" },
] as const;

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;

interface AuthFailure {
  message: string;
  reference?: string;
}

function describeLoginError(error: unknown): AuthFailure {
  if (isApiError(error)) {
    if (error.status === 429 || error.code === "RATE_LIMITED") {
      return { message: "Too many attempts. Wait a minute and try again." };
    }
    if (error.status === 401 || error.code === "AUTH_INVALID") {
      return { message: "Invalid email or password." };
    }
    return { message: error.message, reference: error.correlationId };
  }
  return { message: "Unexpected error. Try again." };
}

// Chuỗi class viết đầy đủ để Tailwind quét được.
const INPUT =
  "w-full rounded-control border bg-surface px-3 py-2 text-body text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine disabled:opacity-60";
const INPUT_INVALID = "border-risk-predictedLate-fg";

export interface SignInProps {
  /** Mặc định lấy từ config; truyền vào khi test. */
  env?: string;
}

export function SignIn({ env = APP_ENV }: SignInProps) {
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [failure, setFailure] = useState<AuthFailure | null>(null);
  const [loading, setLoading] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  function chooseDemo(address: string) {
    setEmail(address);
    setFieldErrors({});
    setFailure(null);
    passwordRef.current?.focus();
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading) {
      return;
    }
    const trimmed = email.trim();
    const errors = {
      email: EMAIL_PATTERN.test(trimmed) ? undefined : "Enter a valid email address.",
      password: password ? undefined : "Enter your password.",
    };
    setFieldErrors(errors);
    setFailure(null);
    if (errors.email || errors.password) {
      (errors.email ? emailRef : passwordRef).current?.focus();
      return;
    }

    setLoading(true);
    try {
      const response = await login({ email: trimmed, password });
      setAuth(response, trimmed.toLowerCase());
    } catch (error) {
      setFailure(describeLoginError(error));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div data-screen="SignIn" className="flex min-h-screen flex-col bg-stone">
      <DemoBanner env={env} context="Pick a demo account to explore each role." />
      <main className="grid flex-1 md:grid-cols-2">
        {/* Nửa trái: nền deepPine (03 mục 5.0) */}
        <section aria-label="About CFO" className="flex flex-col justify-between gap-12 bg-deepPine p-8 text-surface md:p-12">
          <div>
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-overline uppercase text-apricot">CFO</span>
              <span className="text-body text-surface">Central Fulfillment Orchestration</span>
            </div>
            <p className="mt-12 font-mono text-overline uppercase text-apricot">ORDER-TO-DELIVERY ORCHESTRATION</p>
            <p className="mt-3 text-h1">Make every order a reliable, visible promise.</p>
            <p className="mt-4 max-w-md text-body text-surface/80">
              CFO connects live stock, warehouse capacity and fleet availability, so every order gets a delivery date you can keep and everyone can see why.
            </p>
            <div className="mt-8 flex flex-col gap-4">
              {PILLARS.map((pillar) => (
                <div key={pillar.no} className="flex items-baseline gap-4">
                  <span className="font-mono text-caption text-apricot">{pillar.no}</span>
                  <span className="text-h3">{pillar.title}</span>
                </div>
              ))}
            </div>
          </div>
          <p className="font-mono text-caption text-surface/70">Sweden pilot · synthetic data · v0.1-demo</p>
        </section>

        {/* Nửa phải: nền stone */}
        <section className="flex flex-col justify-center p-8 md:p-12">
          <div className="w-full max-w-lg">
            <h1 className="text-h2 text-ink">Sign in</h1>
            <p className="mt-1 text-body text-inkMuted">Use your work account. Access follows your role.</p>

        <form noValidate onSubmit={(event) => void onSubmit(event)} className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="signin-email" className="text-caption font-semibold text-ink">
              Email
            </label>
            <input
              id="signin-email"
              ref={emailRef}
              type="email"
              placeholder="name@company.se"
              autoComplete="username"
              value={email}
              disabled={loading}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={fieldErrors.email ? true : undefined}
              aria-describedby={fieldErrors.email ? "signin-email-error" : undefined}
              className={`${INPUT} ${fieldErrors.email ? INPUT_INVALID : ""}`}
            />
            {fieldErrors.email && (
              <p id="signin-email-error" className="text-caption text-risk-predictedLate-fg">
                {fieldErrors.email}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="signin-password" className="text-caption font-semibold text-ink">
              Password
            </label>
            <input
              id="signin-password"
              ref={passwordRef}
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={loading}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={fieldErrors.password ? true : undefined}
              aria-describedby={fieldErrors.password ? "signin-password-error" : undefined}
              className={`${INPUT} ${fieldErrors.password ? INPUT_INVALID : ""}`}
            />
            {fieldErrors.password && (
              <p id="signin-password-error" className="text-caption text-risk-predictedLate-fg">
                {fieldErrors.password}
              </p>
            )}
          </div>

          {failure && (
            <div role="alert" className="rounded-control border border-risk-predictedLate-bg bg-risk-lateRow p-3 text-body text-risk-predictedLate-fg">
              <p>{failure.message}</p>
              {failure.reference && <p className="mt-1 font-mono text-caption text-inkMuted">Reference {failure.reference}</p>}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            aria-busy={loading}
            className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-apricot disabled:opacity-60"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

            {isDemoEnv(env) && (
              <section aria-labelledby="demo-accounts-title" className="mt-10">
                <h2 id="demo-accounts-title" className="text-h3 text-ink">
                  Demo accounts
                </h2>
                <p className="mt-1 text-caption text-inkMuted">Choose an account to fill in the email, then enter the shared demo password.</p>
                <ul aria-label="Demo accounts" className="mt-4 grid gap-3 sm:grid-cols-2">
                  {DEMO_ACCOUNTS.map((account) => (
                    <li key={account.email}>
                      <button
                        type="button"
                        disabled={loading}
                        onClick={() => chooseDemo(account.email)}
                        className="flex h-full w-full items-start justify-between gap-2 rounded-card border bg-surface p-4 text-left shadow-card hover:bg-rowHover focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine disabled:opacity-60"
                      >
                        <span className="flex flex-col gap-0.5">
                          <span className="text-h3 text-ink">{account.title}</span>
                          <span className="text-caption text-inkMuted">{account.hint}</span>
                          <span className="mt-1 font-mono text-caption text-inkMuted">{account.email}</span>
                        </span>
                        <span aria-hidden="true" className="text-h3 text-pine">
                          →
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <p className="mt-10 text-caption text-inkMuted">
              Customers have no login. They receive order status and ETA by email or SMS — never driver location.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
