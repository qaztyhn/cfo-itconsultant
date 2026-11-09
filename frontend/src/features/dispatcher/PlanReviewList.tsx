/**
 * Entry point for Plan Review. The Order Queue provides the live PLANNED
 * orders and resolves each review using the server-issued planning-run ID.
 * Redirect rather than show the former blank placeholder screen.
 */
import { Navigate } from "react-router-dom";
import { PATHS } from "../../app/access";

export function PlanReviewList() {
  return <Navigate to={`${PATHS.dispatcherOrders}?status=PLANNED`} replace />;
}
