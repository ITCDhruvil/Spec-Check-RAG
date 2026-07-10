import type { ChatMessage } from "@/lib/types/chat";

export function getFollowUpQuestions(messages: ChatMessage[]): string[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== "assistant") continue;
    const raw = msg.model_metadata?.follow_up_questions;
    if (!Array.isArray(raw)) return [];
    return raw
      .filter((q): q is string => typeof q === "string" && q.trim().length > 0)
      .map((q) => q.trim())
      .slice(0, 4);
  }
  return [];
}
