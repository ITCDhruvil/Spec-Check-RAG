import { apiClient } from "@/lib/api/client";
import type {
  AuthUser,
  ChangePasswordPayload,
  ChangePasswordResponse,
  CreateUserPayload,
  CreateUserResponse,
  LoginResponse,
  PaginatedUsers,
  UpdateUserPayload,
  UpdateUserResponse,
} from "@/lib/types/auth";

export async function login(email: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/login/", { email, password });
  return data;
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>("/auth/me/");
  return data;
}

export async function changePassword(payload: ChangePasswordPayload): Promise<ChangePasswordResponse> {
  const { data } = await apiClient.post<ChangePasswordResponse>(
    "/auth/me/change-password/",
    payload
  );
  return data;
}

export async function refreshAccessToken(refresh: string): Promise<{ access: string }> {
  const { data } = await apiClient.post<{ access: string }>("/auth/token/refresh/", { refresh });
  return data;
}

export async function listUsers(): Promise<PaginatedUsers> {
  const { data } = await apiClient.get<PaginatedUsers>("/auth/users/");
  return data;
}

export async function createUser(payload: CreateUserPayload): Promise<CreateUserResponse> {
  const { data } = await apiClient.post<CreateUserResponse>("/auth/users/", payload);
  return data;
}

export async function updateUser(
  id: number,
  payload: UpdateUserPayload
): Promise<UpdateUserResponse> {
  const { data } = await apiClient.patch<UpdateUserResponse>(`/auth/users/${id}/`, payload);
  return data;
}

export async function deleteUser(id: number): Promise<void> {
  await apiClient.delete(`/auth/users/${id}/`);
}

export async function impersonateUser(id: number): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>(`/auth/login-as/${id}/`);
  return data;
}

export async function generatePassword(): Promise<string> {
  const { data } = await apiClient.get<{ password: string }>("/auth/users/generate-password/");
  return data.password;
}
