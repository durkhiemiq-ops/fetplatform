import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// NOTE: @tanstack/react-query-devtools was removed from this provider.
//
// It was mounted unconditionally, so the dev-only inspector (which pulls in
// solid-js and @solid-primitives) shipped in the production bundle. The
// package also has no `?react` subpath export at the installed version
// (5.103.2), so it cannot simply be code-split that way.
//
// It was also dead: there are zero useQuery/useMutation call sites anywhere in
// src/ -- every screen fetches with useState + useEffect against the clients in
// lib/*.js. React Query itself is kept because it is a cheap, correct provider
// to have in place for Wave 1+, but the devtools are gone from the bundle.
//
// If React Query is adopted, add the devtools back behind a
// `import.meta.env.DEV` dynamic import and upgrade the package to a version
// that exposes the split entry.

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function QueryProvider({ children }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}