import type { QueryClient } from "@tanstack/react-query";

import type { ManagedUser, PaginatedUsers } from "@/lib/types/auth";

export function resolveDisplayPassword(
  user: Partial<ManagedUser> & { generated_password?: string | null }
): string | null {
  const value = user.display_password ?? user.generated_password ?? null;
  return value?.trim() ? value.trim() : null;
}

export function patchUserInCache(
  queryClient: QueryClient,
  updated: Partial<ManagedUser> & { id: number; generated_password?: string | null }
) {
  const display_password = resolveDisplayPassword(updated);

  queryClient.setQueryData<PaginatedUsers>(["users"], (current) => {
    if (!current) return current;

    const results = current.results.map((row) =>
      row.id === updated.id
        ? {
            ...row,
            ...updated,
            display_password: display_password ?? row.display_password ?? null,
          }
        : row
    );

    return { ...current, results };
  });
}

export function prependUserInCache(queryClient: QueryClient, created: ManagedUser) {
  const display_password = resolveDisplayPassword(created);

  queryClient.setQueryData<PaginatedUsers>(["users"], (current) => {
    if (!current) {
      return {
        count: 1,
        next: null,
        previous: null,
        results: [{ ...created, display_password }],
      };
    }

    const withoutDuplicate = current.results.filter((row) => row.id !== created.id);
    return {
      ...current,
      count: current.count + 1,
      results: [{ ...created, display_password }, ...withoutDuplicate],
    };
  });
}
