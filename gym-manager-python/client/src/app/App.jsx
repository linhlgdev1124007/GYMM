import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { AppLayout } from "../components/layout/AppLayout";
import { LoginPage } from "../pages/LoginPage";

const DashboardPage = lazy(() =>
  import("../features/dashboard/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const MembersPage = lazy(() =>
  import("../features/members/MembersPage").then((module) => ({
    default: module.MembersPage,
  })),
);
const MemberDetailPage = lazy(() =>
  import("../features/members/MemberDetailPage").then((module) => ({
    default: module.MemberDetailPage,
  })),
);
const MembershipsPage = lazy(() =>
  import("../features/memberships/MembershipsPage").then((module) => ({
    default: module.MembershipsPage,
  })),
);
const PlansPage = lazy(() =>
  import("../features/memberships/PlansPage").then((module) => ({
    default: module.PlansPage,
  })),
);
const TrainersPage = lazy(() =>
  import("../features/trainers/TrainersPage").then((module) => ({
    default: module.TrainersPage,
  })),
);
const TrainingPage = lazy(() =>
  import("../features/training/TrainingPage").then((module) => ({
    default: module.TrainingPage,
  })),
);
const CheckinPage = lazy(() =>
  import("../features/checkins/CheckinPage").then((module) => ({
    default: module.CheckinPage,
  })),
);
const PaymentsPage = lazy(() =>
  import("../features/payments/PaymentsPage").then((module) => ({
    default: module.PaymentsPage,
  })),
);
const ReportsPage = lazy(() =>
  import("../features/reports/ReportsPage").then((module) => ({
    default: module.ReportsPage,
  })),
);
const InventoryPage = lazy(() =>
  import("../features/inventory/InventoryPage").then((module) => ({
    default: module.InventoryPage,
  })),
);
const SettingsPage = lazy(() =>
  import("../features/settings/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const AuditLogPage = lazy(() =>
  import("../features/audit/AuditLogPage").then((module) => ({
    default: module.AuditLogPage,
  })),
);
const AccountsPage = lazy(() =>
  import("../features/users/AccountsPage").then((module) => ({
    default: module.AccountsPage,
  })),
);

export function App() {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="app-loading">
        <div className="brand-mark">
          <span />
        </div>
        <p>Đang tải không gian làm việc…</p>
      </div>
    );
  if (!user) return <LoginPage />;
  const allowed = (roles, element) =>
    roles.includes(user.role) ? element : <Navigate to="/dashboard" replace />;
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <div className="skeleton h-8 w-52" />
          <div className="skeleton h-10 w-full" />
          <div className="skeleton h-64 w-full" />
        </div>
      }
    >
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="members" element={<MembersPage />} />
          <Route path="members/:memberId" element={<MemberDetailPage />} />
          <Route path="memberships" element={allowed(["admin", "manager", "receptionist"], <MembershipsPage />)} />
          <Route
            path="plans"
            element={allowed(["admin", "manager"], <PlansPage />)}
          />
          <Route
            path="trainers"
            element={allowed(["admin", "manager"], <TrainersPage />)}
          />
          <Route path="training" element={<TrainingPage />} />
          <Route path="check-in" element={allowed(["admin", "manager", "receptionist"], <CheckinPage />)} />
          <Route path="payments" element={allowed(["admin", "manager", "receptionist"], <PaymentsPage />)} />
          <Route path="inventory" element={allowed(["admin"], <InventoryPage />)} />
          <Route
            path="reports"
            element={allowed(["admin", "manager"], <ReportsPage />)}
          />
          <Route
            path="settings"
            element={allowed(["admin"], <SettingsPage />)}
          />
          <Route
            path="audit-logs"
            element={allowed(["admin"], <AuditLogPage />)}
          />
          <Route
            path="accounts"
            element={allowed(["admin"], <AccountsPage />)}
          />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
