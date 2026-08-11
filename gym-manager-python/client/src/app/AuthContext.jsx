import { createContext, useContext } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { notify } from "../services/notify";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const userQuery = useQuery({
    queryKey: ["auth"],
    queryFn: () => api("/api/auth/me"),
    retry: false,
    staleTime: 60_000,
  });
  const loginMutation = useMutation({
    mutationFn: (credentials) =>
      api("/api/auth/login", { method: "POST", body: credentials }),
    onSuccess: (data) => queryClient.setQueryData(["auth"], data.user),
  });
  const logoutMutation = useMutation({
    mutationFn: () => api("/api/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(["auth"], null);
    },
    onError: (error) =>
      notify.errorFrom(error, "Không thể đăng xuất. Vui lòng thử lại."),
  });
  return (
    <AuthContext.Provider
      value={{
        user: userQuery.data,
        loading: userQuery.isLoading,
        login: loginMutation.mutateAsync,
        loginPending: loginMutation.isPending,
        logout: logoutMutation.mutateAsync,
        logoutPending: logoutMutation.isPending,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
