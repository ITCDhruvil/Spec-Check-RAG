import { apiClient } from "@/lib/api/client";

export type FeatureSettings = {
  features: Record<string, string[]>;
  defaults: Record<string, string[]>;
  my_features: string[];
  editable: boolean;
};

export async function getFeatureSettings(): Promise<FeatureSettings> {
  const { data } = await apiClient.get<FeatureSettings>("/settings/features/");
  return data;
}

export async function updateFeatureSettings(
  updates: Record<string, string[]>
): Promise<Record<string, string[]>> {
  const { data } = await apiClient.patch("/settings/features/", updates);
  return data;
}
