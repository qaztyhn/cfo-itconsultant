/**
 * Hiển thị khi tài khoản không có không gian làm việc nào hoặc route bị chặn mà không có nơi chuyển về.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { signOut } from "./session";

export function NoAccess() {
  return (
    <main className="mx-auto flex min-h-screen max-w-content flex-col items-start justify-center gap-4 p-8">
      <p className="font-mono text-overline uppercase text-inkMuted">Access</p>
      <h1 className="text-h1">No workspace for this account</h1>
      <p className="text-body text-inkMuted">Your account is signed in but has no screens assigned. Ask an administrator to review your roles.</p>
      <button type="button" onClick={() => void signOut()} className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white">
        Sign out
      </button>
    </main>
  );
}