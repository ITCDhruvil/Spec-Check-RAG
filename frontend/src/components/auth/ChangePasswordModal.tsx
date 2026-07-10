"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Modal } from "@/components/ui/Modal";
import { changePassword } from "@/lib/api/auth";
import { patchUserInCache } from "@/lib/users-cache";
import { useAuth } from "@/providers/auth-provider";

type ChangePasswordModalProps = {
  open: boolean;
  onClose: () => void;
};

export function ChangePasswordModal({ open, onClose }: ChangePasswordModalProps) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function resetForm() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError(null);
    setSuccess(null);
  }

  function handleClose() {
    resetForm();
    onClose();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (newPassword.length < 10) {
      setError("New password must be at least 10 characters.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      if (user?.is_admin && response.user) {
        patchUserInCache(queryClient, response.user);
      }
      setSuccess("Password updated. Use your new password next time you sign in.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Change password"
      description="Choose any password you want (minimum 10 characters)."
    >
      <form onSubmit={handleSubmit} className="space-y-4 px-2 pb-2">
        <div>
          <label htmlFor="current-password" className="block text-sm font-medium text-ink">
            Current password
          </label>
          <input
            id="current-password"
            type="password"
            autoComplete="current-password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="new-password" className="block text-sm font-medium text-ink">
            New password
          </label>
          <input
            id="new-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border px-3 py-2 text-sm"
          />
        </div>

        <div>
          <label htmlFor="confirm-password" className="block text-sm font-medium text-ink">
            Confirm new password
          </label>
          <input
            id="confirm-password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="mt-1 w-full rounded-lg border border-surface-border px-3 py-2 text-sm"
          />
        </div>

        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {success && (
          <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            {success}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg border border-surface-border px-3 py-2 text-sm font-medium text-ink hover:bg-surface-muted"
          >
            {success ? "Close" : "Cancel"}
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60"
          >
            {submitting ? "Saving…" : "Save password"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
