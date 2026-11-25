import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AuthProvider } from "./auth/AuthProvider";
import { clearJobs } from "./features/upload/uploader";
import type { AuthService } from "./auth/types";
import { makeQueryClient } from "./queryClient";
import { routes } from "./routes/routes";

export function App({ authService }: { authService: AuthService }) {
  const [queryClient] = useState(makeQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider service={authService} onSignOut={clearJobs}>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
