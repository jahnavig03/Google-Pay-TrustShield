import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";

import { AnalystLayout, BareLayout, CustomerLayout } from "./components/Layout";
import { AnalystLogin, RequireAnalyst, SignOut } from "./pages/AnalystLogin";
import { AnalystPage } from "./pages/AnalystPage";
import { CustomerHome } from "./pages/CustomerHome";
import { LandingPage } from "./pages/LandingPage";
import { MerchantPage } from "./pages/MerchantPage";
import { PayPage } from "./pages/PayPage";
import { PhoneAppPage } from "./phone/PhoneApp";
import { RoleProvider } from "./role";
import { SessionProvider } from "./session";
import { ThemeProvider } from "./theme";

export function AppRoutes() {
  return (
    <Routes>
      {/* Entry screens */}
      <Route element={<BareLayout />}>
        <Route index element={<LandingPage />} />
        <Route path="customer" element={<CustomerHome />} />
        <Route path="analyst/login" element={<AnalystLogin />} />
      </Route>

      {/* Customer panel: phone app, payment check, merchant check */}
      <Route element={<CustomerLayout />}>
        <Route path="customer/app" element={<PhoneAppPage />} />
        <Route path="customer/pay" element={<PayPage />} />
        <Route path="customer/merchant" element={<MerchantPage />} />
      </Route>

      {/* Analyst panel: only after sign-in */}
      <Route
        element={
          <RequireAnalyst>
            <AnalystLayout />
          </RequireAnalyst>
        }
      >
        <Route path="analyst" element={<AnalystPage />} />
        <Route path="analyst/:caseId" element={<AnalystPage />} />
      </Route>

      <Route path="signout" element={<SignOut />} />

      {/* Old links */}
      <Route path="pay" element={<Navigate to="/customer/pay" replace />} />
      <Route path="merchant" element={<Navigate to="/customer/merchant" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

export function App({ queryClient = makeQueryClient() }: { queryClient?: QueryClient }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <SessionProvider>
          <RoleProvider>
            <AppRoutes />
          </RoleProvider>
        </SessionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
