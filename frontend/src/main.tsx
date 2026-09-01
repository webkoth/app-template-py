import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "@tanstack/react-router"
import { buildRouter } from "@/router"
import "@/index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Приложение внутреннее: перезапрашивать при каждом возврате во
      // вкладку незачем, данные меняются раз в час, а не раз в секунду.
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
})

const router = buildRouter(queryClient)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
