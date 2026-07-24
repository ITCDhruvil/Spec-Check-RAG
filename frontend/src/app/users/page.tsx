"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { UserActionsMenu } from "@/components/users/UserActionsMenu";
import {
  createUser,
  generatePassword,
  impersonateUser,
  listUsers,
  updateUser,
} from "@/lib/api/auth";
import { SpokesLoader } from "@/components/ui/Spokes";
import { usePageHeader } from "@/lib/pageHeaderContext";
import { useAuth } from "@/providers/auth-provider";
import { patchUserInCache, prependUserInCache } from "@/lib/users-cache";
import { copyToClipboard } from "@/lib/copyToClipboard";
import type { CreateUserPayload, ManagedUser, UserRole } from "@/lib/types/auth";

function formatDate(value: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function EyeIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
      <line x1="2" x2="22" y1="2" y2="22" />
    </svg>
  );
}

function CopyIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function PasswordCell({
  password,
  onSetPassword,
}: {
  password: string | null | undefined;
  onSetPassword?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const [visible, setVisible] = useState(false);
  if (!password?.trim()) {
    return (
      <button
        type="button"
        onClick={onSetPassword}
        className="text-xs font-medium text-accent hover:underline"
      >
        Set password
      </button>
    );
  }

  const value = password.trim();

  async function copyPassword() {
    setCopyError(false);
    const ok = await copyToClipboard(value);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } else {
      setCopyError(true);
      setTimeout(() => setCopyError(false), 2000);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <code className="rounded bg-surface-muted px-2 py-1 text-xs text-ink">
        {visible ? value : "•".repeat(Math.min(value.length, 12))}
      </code>
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        title={visible ? "Hide password" : "Show password"}
        aria-label={visible ? "Hide password" : "Show password"}
        className="rounded border border-surface-border p-1 text-ink-muted hover:bg-surface-muted"
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
      <button
        type="button"
        onClick={copyPassword}
        title={copied ? "Copied" : copyError ? "Copy failed — select and copy manually" : "Copy password"}
        aria-label={copied ? "Copied" : copyError ? "Copy failed" : "Copy password"}
        className="rounded border border-surface-border p-1 text-ink-muted hover:bg-surface-muted"
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    </div>
  );
}

function SetPasswordModal({
  user,
  open,
  onClose,
}: {
  user: ManagedUser | null;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setPassword("");
      setError(null);
    }
  }, [open, user?.id]);

  async function handleGenerate() {
    try {
      setPassword(await generatePassword());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate password");
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!user) return;

    const next = password.trim();
    if (next.length < 10) {
      setError("Password must be at least 10 characters.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const data = await updateUser(user.id, { password: next });
      patchUserInCache(queryClient, data);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Change password"
      description={user ? user.email : undefined}
    >
      <form onSubmit={handleSubmit} className="space-y-4 px-2 pb-2">
        <div className="flex gap-2">
          <input
            type="text"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={10}
            placeholder="At least 10 characters"
            className="flex-1 rounded-lg border border-surface-border bg-surface px-3 py-2 font-mono text-sm text-ink"
          />
          <button
            type="button"
            onClick={handleGenerate}
            className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            Generate
          </button>
        </div>

        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60"
          >
            {submitting ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// Admin is unique (the configured admin account) — never assignable here.
const ROLE_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "user", label: "General User" },
  { value: "team_leader", label: "Team Leader" },
  { value: "manager", label: "Manager" },
];

function CreateUserForm() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [role, setRole] = useState<UserRole>("user");
  const [password, setPassword] = useState("");
  const [useCustomPassword, setUseCustomPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: CreateUserPayload) => createUser(payload),
    onSuccess: (data) => {
      prependUserInCache(queryClient, data);
      setUsername("");
      setEmail("");
      setFirstName("");
      setLastName("");
      setRole("user");
      setPassword("");
      setUseCustomPassword(false);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  async function handleGenerate() {
    try {
      const generated = await generatePassword();
      setPassword(generated);
      setUseCustomPassword(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate password");
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    const payload: CreateUserPayload = {
      username: username.trim(),
      email: email.trim(),
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      role,
    };

    if (useCustomPassword && password.trim()) {
      if (password.trim().length < 10) {
        setError("Password must be at least 10 characters.");
        return;
      }
      payload.password = password.trim();
    }

    mutation.mutate(payload);
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-surface-border bg-surface p-6">
      <h2 className="text-lg font-semibold text-ink">Create user</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Add a new account. A secure password is generated automatically unless you provide one.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-ink">Username</label>
          <input
            required
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink">Email</label>
          <input
            required
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink">First name</label>
          <input
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink">Last name</label>
          <input
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-ink"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink">Role</label>
          <Select
            value={role}
            onChange={setRole}
            options={ROLE_OPTIONS}
            className="mt-1 w-full py-2"
          />
          <p className="mt-1 text-xs text-ink-muted">
            Managers & team leaders see all documents and insights; general users see only their own.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={useCustomPassword}
            onChange={(e) => setUseCustomPassword(e.target.checked)}
          />
          Set a custom password (minimum 10 characters)
        </label>

        {useCustomPassword && (
          <div className="flex gap-2">
            <input
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={10}
              placeholder="At least 10 characters"
              className="flex-1 rounded-lg border border-surface-border bg-surface px-3 py-2 font-mono text-sm text-ink"
            />
            <button
              type="button"
              onClick={handleGenerate}
              className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
            >
              Generate
            </button>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={mutation.isPending}
        className="mt-6 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60"
      >
        {mutation.isPending ? "Creating…" : "Create user"}
      </button>
    </form>
  );
}

function UserRow({
  user,
  currentUserId,
  onLoginAs,
  onSetPassword,
  loginAsBusy,
}: {
  user: ManagedUser;
  currentUserId?: number;
  onLoginAs: (user: ManagedUser) => void;
  onSetPassword: (user: ManagedUser) => void;
  loginAsBusy: boolean;
}) {
  const queryClient = useQueryClient();

  const changeRole = useMutation({
    mutationFn: (role: UserRole) => updateUser(user.id, { role }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <tr className="border-t border-surface-border">
      <td className="px-4 py-3 text-sm">
        <div className="font-medium text-ink">{user.username}</div>
        <div className="text-ink-muted">{user.email}</div>
      </td>
      <td className="px-4 py-3 text-sm text-ink-muted">
        {[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"}
      </td>
      <td className="px-4 py-3 text-sm">
        <PasswordCell
          password={user.display_password}
          onSetPassword={() => onSetPassword(user)}
        />
      </td>
      <td className="px-4 py-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${
              user.is_active
                ? "border-green-200 bg-green-100 text-green-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
                : "border-surface-border bg-surface-muted text-ink-muted"
            }`}
          >
            {user.is_active ? "Active" : "Disabled"}
          </span>
          {user.is_admin ? (
            <span className="inline-flex rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
              Admin
            </span>
          ) : (
            <Select
              value={user.role ?? "user"}
              disabled={changeRole.isPending}
              onChange={(role) => changeRole.mutate(role)}
              options={ROLE_OPTIONS.filter((r) => r.value !== "admin")}
              title="Change role"
            />
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-ink-muted">{formatDate(user.last_login)}</td>
      <td className="px-4 py-3 text-right text-sm">
        <UserActionsMenu
          user={user}
          currentUserId={currentUserId}
          onLoginAs={onLoginAs}
          onSetPassword={onSetPassword}
          loginAsBusy={loginAsBusy}
        />
      </td>
    </tr>
  );
}

export default function UsersPage() {
  const { user, loading, applySession } = useAuth();
  const router = useRouter();
  const [loginAsBusyId, setLoginAsBusyId] = useState<number | null>(null);
  const [setPasswordUser, setSetPasswordUser] = useState<ManagedUser | null>(null);

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
    enabled: !!user?.is_admin,
  });

  // Page header renders in the AppShell top bar (replaces the brand block).
  usePageHeader({
    backHref: "/",
    backLabel: "Dashboard",
    title: "User management",
    subtitle: "Create and manage platform accounts",
  });

  useEffect(() => {
    if (!loading && user && !user.is_admin) {
      router.replace("/");
    }
  }, [user, loading, router]);

  async function handleLoginAs(target: ManagedUser) {
    setLoginAsBusyId(target.id);
    try {
      const session = await impersonateUser(target.id);
      applySession(session);
      router.push("/");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Could not sign in as user.");
    } finally {
      setLoginAsBusyId(null);
    }
  }

  if (loading || !user?.is_admin) {
    return loading ? (
      <SpokesLoader className="py-24" />
    ) : (
      <div className="py-12 text-center text-ink-muted">Redirecting…</div>
    );
  }

  const users = usersQuery.data?.results ?? [];

  return (
    <div className="space-y-8">
      <SetPasswordModal
        user={setPasswordUser}
        open={setPasswordUser !== null}
        onClose={() => setSetPasswordUser(null)}
      />

      <CreateUserForm />

      <div className="rounded-lg border border-surface-border bg-surface">
        <div className="border-b border-surface-border px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">All users ({usersQuery.data?.count ?? users.length})</h2>
        </div>

        {usersQuery.isLoading ? (
          <p className="px-4 py-8 text-sm text-ink-muted">Loading users…</p>
        ) : usersQuery.isError ? (
          <p className="px-4 py-8 text-sm text-red-600 dark:text-red-300">Failed to load users.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead className="bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">User</th>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Password</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last login</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((managedUser) => (
                  <UserRow
                    key={managedUser.id}
                    user={managedUser}
                    currentUserId={user.id}
                    onLoginAs={handleLoginAs}
                    onSetPassword={setSetPasswordUser}
                    loginAsBusy={loginAsBusyId === managedUser.id}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
