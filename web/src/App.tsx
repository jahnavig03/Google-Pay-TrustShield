import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import type { Role } from "./api/client";
import { Layout } from "./components/Layout";
import { AnalystPage } from "./pages/AnalystPage";
import { MerchantPage } from "./pages/MerchantPage";
import { PayPage } from "./pages/PayPage";
import { RoleProvider } from "./role";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/pay" replace />} />
        <Route path="pay" element={<PayPage />} />
        <Route path="analyst" element={<AnalystPage />} />
        <Route path="analyst/:caseId" element={<AnalystPage />} />
        <Route path="merchant" element={<MerchantPage />} />
        <Route path="*" element={<Navigate to="/pay" replace />} />
      </Route>
    </Routes>
  );
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

export function App({
  queryClient = makeQueryClient(),
  initialRole,
}: {
  queryClient?: QueryClient;
  initialRole?: Role;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <RoleProvider initialRole={initialRole}>
        <AppRoutes />
      </RoleProvider>
    </QueryClientProvider>
  );
}
