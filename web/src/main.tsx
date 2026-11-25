import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "./api/client";
import { startMonitoring } from "./lib/monitor";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AuthProvider } from "./auth";
import { ThemeSync } from "./ThemeSync";
import { ToastProvider } from "./ui/kit";
import "./styles.css";

// a read that fails on the network or a server error is tried once more before the page shows the error
const retry = (n: number, e: unknown) => n < 1 && !(e instanceof ApiError && e.status < 500);
const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry } } });

void startMonitoring();                 // off unless VITE_SENTRY_DSN is set

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <ThemeSync />
            <App />
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
