/**
 * A14 CS · Order lookup — tra cứu đơn, trạng thái, ETA; KHÔNG GPS/điểm số (docs/03 A14).
 * Tìm kiếm gọi GET /orders?q= khi bấm submit (không theo từng phím). Chưa claim tìm theo phone: DEC-CS-SEARCH-20261109 chờ backend.
 * Phân trang Previous/Next theo page/page_size của GET /orders; đổi từ khoá thì về trang 1.
 * Owner: Dev 3 (luồng C) — M8.
 */
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { PageHeader } from "../../components/PageHeader";
import { RiskChip } from "../../components/RiskChip";
import { EmptyState, ErrorState, LoadingState } from "../../components/StateViews";
import { StatusChip } from "../../components/StatusChip";
import { csKeys, SEARCH_PAGE_SIZE, searchOrders } from "./api";
import { SEARCH_PLACEHOLDER } from "./constants";
import { toOrderStatus, toRiskColor } from "./format";
import { OrderDetail } from "./OrderDetail";
import { EtaForecasts } from "./EtaForecasts";
import { NotificationHistory } from "./NotificationHistory";
import { OrderTimeline } from "./OrderTimeline";
import { ContactLogDemo } from "./ContactLogDemo";

const PAGER_BUTTON =
  "rounded-control border bg-surface px-3 py-2 text-body text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine";

export function OrderLookup() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const inputId = useId();

  const search = useQuery({
    queryKey: csKeys.search(query, page),
    queryFn: ({ signal }) => searchOrders(query, signal, page),
    enabled: query !== "",
    retry: false,
    refetchInterval: false,
    // Chuyển trang của cùng một từ khoá: giữ danh sách cũ trong lúc tải (không nháy, không mất focus).
    // Đổi từ khoá thì không giữ, tránh hiện kết quả của từ khoá cũ.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[3] === query ? previous : undefined),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = input.trim();
    if (!next) return;
    const sameSearch = next === query && page === 1;
    setSelectedId(null);
    setQuery(next);
    setPage(1);
    if (sameSearch) void search.refetch();
  }

  function renderResults() {
    if (query === "") {
      return <EmptyState message="Search for an order to see its status, ETA and notifications." />;
    }
    if (search.isPending) {
      return <LoadingState rows={4} rowClassName="h-[72px]" />;
    }
    if (search.isError) {
      return <ErrorState error={search.error} title="Search failed" onRetry={() => void search.refetch()} />;
    }
    const { items, total } = search.data;
    // Số trang lấy từ dữ liệu đang hiển thị (có thể là trang cũ trong lúc tải trang mới).
    const shownPage = search.data.page;
    if (items.length === 0 && shownPage === 1) {
      return <EmptyState message="No orders match this search." />;
    }
    const pageSize = search.data.pageSize > 0 ? search.data.pageSize : SEARCH_PAGE_SIZE;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const first = (shownPage - 1) * pageSize + 1;
    const range = shownPage === 1 && items.length === total ? `${items.length}` : `${first}–${first + items.length - 1}`;
    const atFirst = shownPage <= 1;
    const atLast = shownPage >= totalPages;
    return (
      <div className="flex flex-col gap-3">
        <p className="text-caption text-inkMuted">
          {items.length === 0 ? "No orders on this page." : `Showing ${range} of ${total} ${total === 1 ? "order" : "orders"}`}
        </p>
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={item.id === selectedId}
                onClick={() => setSelectedId(item.id)}
                className={[
                  "flex w-full flex-col items-start gap-2 rounded-card border bg-surface px-4 py-3 text-left hover:bg-rowHover",
                  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine",
                  item.id === selectedId ? "border-pine" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <span className="font-mono text-body font-semibold text-ink">{item.orderNo}</span>
                <span className="text-body text-inkMuted">{item.customerName ?? "—"}</span>
                <span className="flex flex-wrap items-center gap-2">
                  {item.status && <StatusChip status={toOrderStatus(item.status)} />}
                  <RiskChip color={toRiskColor(item.riskColor)} />
                </span>
              </button>
            </li>
          ))}
        </ul>
        {totalPages > 1 && (
          <nav aria-label="Search results pages" className="flex items-center justify-between gap-2">
            <button
              type="button"
              aria-disabled={atFirst}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className={`${PAGER_BUTTON}${atFirst ? " opacity-50" : ""}`}
            >
              Previous
            </button>
            <span className="text-caption text-inkMuted">
              Page {shownPage} of {totalPages}
            </span>
            <button
              type="button"
              aria-disabled={atLast}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              className={`${PAGER_BUTTON}${atLast ? " opacity-50" : ""}`}
            >
              Next
            </button>
          </nav>
        )}
      </div>
    );
  }

  const hasResults = !!search.data && search.data.items.length > 0;

  return (
    <section data-screen="OrderLookup" className="flex flex-col gap-6">
      <PageHeader overline="CS" title="Order lookup" description="Find an order and check its status, ETA and notifications." />

      <form role="search" onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor={inputId} className="text-caption font-semibold text-ink">
            Search orders
          </label>
          <input
            id={inputId}
            type="search"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder={SEARCH_PLACEHOLDER}
            autoComplete="off"
            className="rounded-control border bg-surface px-3 py-2 text-body text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-pine"
          />
        </div>
        <button type="submit" className="rounded-control bg-pine px-4 py-2 text-body font-semibold text-white">
          Search
        </button>
      </form>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div aria-live="polite" aria-busy={search.isPlaceholderData}>
          {renderResults()}
        </div>
        <section aria-label="Order details">
          {selectedId !== null ? (
            <div key={selectedId} className="flex flex-col gap-8">
              <OrderDetail orderId={selectedId} />
              <EtaForecasts orderId={selectedId} />
              <NotificationHistory orderId={selectedId} />
              <OrderTimeline orderId={selectedId} />
              <ContactLogDemo />
            </div>
          ) : (
            hasResults && <EmptyState message="Select an order to see its details." />
          )}
        </section>
      </div>
    </section>
  );
}