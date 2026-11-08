/**
 * QueryClient dùng chung toàn app. Cache gắn với phiên đăng nhập: khi token hoặc user.id đổi
 * (logout, 401, hết hạn, hoặc người khác đăng nhập đè) thì hủy request đang chạy và xóa toàn bộ cache,
 * để dữ liệu của người trước (vd. ["orders", "counts"]) không hiện cho người sau.
 * Owner: Dev 3 (luồng C) — M0.
 */
import { QueryClient } from "@tanstack/react-query";
import { useAuthStore } from "./store";

export const queryClient = new QueryClient({ defaultOptions: { queries: { refetchInterval: 20_000 } } });

export function resetQueryCache(): void {
  void queryClient.cancelQueries();
  queryClient.clear();
}

interface Identity {
  token: string | null;
  userId: number | null;
}

function identityOf(state: { token: string | null; user: { id: number } | null }): Identity {
  return { token: state.token, userId: state.user?.id ?? null };
}

let previous = identityOf(useAuthStore.getState());

useAuthStore.subscribe((state) => {
  const current = identityOf(state);
  if (current.token !== previous.token || current.userId !== previous.userId) {
    resetQueryCache();
  }
  previous = current;
});
