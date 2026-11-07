/**
 * Bảng route theo vai trò (docs/04 mục 11). Quy tắc truy cập lấy từ access.ts (cùng nguồn với menu).
 * Route chi tiết (một đơn, một chuyến…) do các task M1–M7 thêm; tiền tố trong access.ts đã phủ sẵn.
 * Owner: Dev 3 (luồng C) — M0.
 */
import type { ReactElement } from "react";
import { Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { OrderLookup } from "../features/cs/OrderLookup"
import { SignIn } from "../features/auth/SignIn";
import { Exceptions } from "../features/dispatcher/Exceptions";
import { OrderQueue } from "../features/dispatcher/OrderQueue";
import { PlanReviewList } from "../features/dispatcher/PlanReviewList";
import { TrackingList } from "../features/dispatcher/TrackingList";
import { Transfers } from "../features/dispatcher/Transfers";
import { TodaysTrips } from "../features/driver/TodaysTrips";
import { DataIntegration } from "../features/it/DataIntegration";
import { Employees } from "../features/it/Employees";
import { HandlingGroups } from "../features/it/HandlingGroups";
import { MarketConfig } from "../features/it/MarketConfig";
import { ProductMapping } from "../features/it/ProductMapping";
import { Users } from "../features/it/Users";
import { Vehicles } from "../features/it/Vehicles";
import { KpiDashboard } from "../features/kpi/KpiDashboard";
import { NotificationInbox } from "../features/notifications/NotificationInbox";
import { Revenue } from "../features/revenue/Revenue";
import { MyStoreOrders } from "../features/store/MyStoreOrders";
import { Attendance } from "../features/warehouse/Attendance";
import { PrepQueue } from "../features/warehouse/PrepQueue";
import { NoAccess } from "./NoAccess";
import { PATHS, ruleFor } from "./access";
import { GuestOnly, LandingRedirect, RequireAccess, RequireAuth } from "./guards";

function guarded(path: string, element: ReactElement): RouteObject {
  return { path, element: <RequireAccess allow={ruleFor(path)}>{element}</RequireAccess> };
}

/** Mục "Contact log" (03 mục 3.2, ASM-H): chưa có component, chỉ giữ chỗ cho tới task CS. */
const ContactLogPlaceholder = <section data-screen="ContactLog" />;

export const appRoutes: RouteObject[] = [
  { path: PATHS.login, element: <GuestOnly><SignIn /></GuestOnly> },
  {
    element: <RequireAuth />,
    children: [
      { path: "/", element: <LandingRedirect /> },
      { path: PATHS.noAccess, element: <NoAccess /> },
      guarded(PATHS.driver, <TodaysTrips />), // PWA riêng, không dùng AppShell/sidebar (03 mục 3.2)
      {
        element: <AppShell />,
        children: [
          guarded(PATHS.dispatcherOrders, <OrderQueue />),
          guarded(PATHS.dispatcherPlanReview, <PlanReviewList />),
          guarded(PATHS.dispatcherExceptions, <Exceptions />),
          guarded(PATHS.dispatcherTracking, <TrackingList />),
          guarded(PATHS.dispatcherTransfers, <Transfers />),
          guarded(PATHS.warehousePrep, <PrepQueue />),
          guarded(PATHS.warehouseAttendance, <Attendance />),
          guarded(PATHS.warehouseTransfers, <Transfers />),
          guarded(PATHS.storeOrders, <MyStoreOrders />),
          guarded(PATHS.csOrders, <OrderLookup />),
          guarded(PATHS.csContacts, ContactLogPlaceholder),
          guarded(PATHS.itIntegration, <DataIntegration />),
          guarded(PATHS.itMapping, <ProductMapping />),
          guarded(PATHS.itHandlingGroups, <HandlingGroups />),
          guarded(PATHS.itEmployees, <Employees />),
          guarded(PATHS.itVehicles, <Vehicles />),
          guarded(PATHS.itUsers, <Users />),
          guarded(PATHS.itMarket, <MarketConfig />),
          guarded(PATHS.notifications, <NotificationInbox />),
          guarded(PATHS.kpi, <KpiDashboard />),
          guarded(PATHS.revenue, <Revenue />),
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
];