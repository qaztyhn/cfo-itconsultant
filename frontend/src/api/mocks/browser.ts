/**
 * MSW browser worker setup. Owner: Dev 3 — M0.
 */
import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);
