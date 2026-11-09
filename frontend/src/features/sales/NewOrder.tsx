/** Sales entry point for an existing POS deployment (docs/03 §5.5, ASM-G).
 * CFO never creates or modifies source POS orders.
 */
import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { POS_URL } from "../../api/config";
import { PATHS } from "../../app/access";

export function NewOrder() {
  return (
    <section data-screen="SalesNewOrder" className="space-y-6">
      <header>
        <p className="font-mono text-xs font-semibold uppercase text-pine">Sales · Source system</p>
        <h1 className="mt-2 text-3xl font-bold text-ink">New order</h1>
        <p className="mt-2 max-w-2xl text-sm text-inkMuted">
          Create and submit an order in your existing POS first. CFO reads submitted orders
          for delivery planning; it does not write orders back to POS.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-card border border-border bg-surface p-6" aria-labelledby="pos-entry-title">
          <p className="font-mono text-overline uppercase text-apricot">01 · Existing POS</p>
          <h2 id="pos-entry-title" className="mt-2 text-xl font-bold text-ink">Create the order in POS</h2>
          <p className="mt-3 text-sm text-inkMuted">
            Enter the customer, requested delivery details and materials, then submit the order
            using your store POS.
          </p>
          {POS_URL ? (
            <a
              href={POS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 inline-flex items-center gap-2 rounded-control bg-pine px-4 py-3 text-sm font-semibold text-surface"
            >
              Open POS <ExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          ) : (
            <p role="status" className="mt-5 rounded-control border border-border bg-stone p-4 text-sm text-ink">
              The POS web application is not configured for this deployment. Use your existing
              store POS or ask an administrator to configure VITE_POS_URL to the deployed POS
              interface (HTTPS). The source API on localhost:8100 is not a POS web page.
            </p>
          )}
        </section>

        <section className="rounded-card border border-border bg-surface p-6" aria-labelledby="pos-sync-title">
          <p className="font-mono text-overline uppercase text-apricot">02 · CFO</p>
          <h2 id="pos-sync-title" className="mt-2 text-xl font-bold text-ink">Check delivery feasibility</h2>
          <p className="mt-3 text-sm text-inkMuted">
            After POS submission, enter its order reference in CFO and run Sync &amp; confirm
            delivery. A delivery promise is not confirmed until an authorized plan is approved.
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link to={PATHS.salesSyncCheck} className="rounded-control bg-pine px-4 py-3 text-sm font-semibold text-surface">
              Sync &amp; confirm delivery
            </Link>
            <Link to={PATHS.storeOrders} className="rounded-control border border-border px-4 py-3 text-sm font-semibold text-pine">
              My store orders
            </Link>
          </div>
        </section>
      </div>
    </section>
  );
}
