export type ChangePasswordPayload = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

export type ChangePasswordResponse = {
  message: string;
  user: ManagedUser;
};

export type UserRole = "admin" | "manager" | "team_leader" | "user";

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
  is_admin: boolean;
  /** Admin / manager / team leader — sees all docs, feedback, insights. */
  is_management: boolean;
  role: UserRole;
};

export type LoginResponse = {
  access: string;
  refresh: string;
  user: AuthUser;
};

export type ManagedUser = AuthUser & {
  display_password?: string | null;
};

export type CreateUserPayload = {
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  password?: string;
  role?: UserRole;
};

export type CreateUserResponse = ManagedUser & {
  generated_password?: string;
};

export type UpdateUserPayload = {
  username?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  is_active?: boolean;
  password?: string;
  regenerate_password?: boolean;
  role?: UserRole;
};

export type UpdateUserResponse = ManagedUser & {
  generated_password?: string;
};

export type PaginatedUsers = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ManagedUser[];
};
