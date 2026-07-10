"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useRef, useState } from "react";

import { AssistantMessageBubble } from "@/components/chat/AssistantMessageBubble";
import { normalizeCitationPage } from "@/lib/citationUtils";
import { getFollowUpQuestions } from "@/lib/chatFollowUps";
import {
  createChatSession,
  getChatIndexStatus,
  getChatSession,
  indexDocumentForChat,
  sendChatMessage,
} from "@/lib/api/chat";
import type { SourceCitation } from "@/lib/types/intelligence";
import type { ChatCitation, ChatMessage } from "@/lib/types/chat";

function NewChatIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path
        d="M2.5 3.5h7.5a1 1 0 011 1v6.5H6.5L4 13v-2H2.5a1 1 0 01-1-1V4.5a1 1 0 011-1z"
        strokeLinejoin="round"
      />
      <path d="M11.5 4.5v7M8 8h7" strokeLinecap="round" />
    </svg>
  );
}

const SUGGESTED_PROMPTS = [
  "What are the submission requirements?",
  "What is the proposal due date?",
  "How will proposals be evaluated?",
  "What forms must be included?",
  "What are the key technical requirements?",
];

function chatCitationsToSources(citations: ChatCitation[]): SourceCitation[] {
  return citations.map((c) => ({
    page: normalizeCitationPage(c.page),
    section: c.section,
    source_text: c.source_text,
    citation_verified: Boolean(c.source_text?.trim()),
    highlightable: c.highlightable !== false,
  }));
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[min(100%,36rem)] rounded-xl bg-accent px-4 py-3 text-sm leading-relaxed text-white shadow-sm">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <AssistantMessageBubble
        content={message.content}
        sources={chatCitationsToSources(message.citations ?? [])}
      />
    </div>
  );
}

export function ChatPanel({ documentId }: { documentId: string }) {
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const indexQuery = useQuery({
    queryKey: ["chat-index", documentId],
    queryFn: () => getChatIndexStatus(documentId),
  });

  const sessionQuery = useQuery({
    queryKey: ["chat-session", documentId, sessionId],
    queryFn: () => getChatSession(documentId, sessionId!),
    enabled: !!sessionId,
  });

  const indexMutation = useMutation({
    mutationFn: () => indexDocumentForChat(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat-index", documentId] });
    },
  });

  const startSessionMutation = useMutation({
    mutationFn: () => createChatSession(documentId),
    onSuccess: (session) => setSessionId(session.id),
  });

  const autoStarted = useRef(false);
  useEffect(() => {
    if (indexQuery.data?.indexed && !sessionId && !autoStarted.current) {
      autoStarted.current = true;
      startSessionMutation.mutate();
    }
  }, [indexQuery.data?.indexed, sessionId, startSessionMutation]);

  const sendMutation = useMutation({
    mutationFn: (text: string) => sendChatMessage(documentId, sessionId!, text),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["chat-session", documentId, sessionId],
      });
      setInput("");
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessionQuery.data?.messages.length, sendMutation.isPending]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || !sessionId || sendMutation.isPending) return;
    sendMutation.mutate(text);
  };

  const sendSuggested = (text: string) => {
    if (!sessionId || sendMutation.isPending) return;
    sendMutation.mutate(text);
  };

  const handleNewChat = () => {
    if (!indexed || startSessionMutation.isPending || sendMutation.isPending) return;
    const previousSessionId = sessionId;
    startSessionMutation.mutate(undefined, {
      onSuccess: (session) => {
        setSessionId(session.id);
        setInput("");
        if (previousSessionId) {
          queryClient.removeQueries({
            queryKey: ["chat-session", documentId, previousSessionId],
          });
        }
      },
    });
  };

  const messages = sessionQuery.data?.messages ?? [];
  const followUpQuestions = getFollowUpQuestions(messages);
  const indexed = indexQuery.data?.indexed;
  const needsIndex = indexQuery.isSuccess && !indexed;
  const ready = Boolean(sessionId && indexed);
  const showFollowUps =
    followUpQuestions.length > 0 && messages.length > 0 && !sendMutation.isPending;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-surface-border bg-surface shadow-sm">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-surface-border px-5 py-4">
        <div>
          <p className="text-sm font-semibold text-ink">Document Q&amp;A</p>
          <p className="mt-0.5 text-xs text-ink-muted">
            Open sources and use the arrow on a citation to jump in the document preview.
          </p>
        </div>
        {ready && messages.length > 0 && (
          <button
            type="button"
            onClick={handleNewChat}
            disabled={startSessionMutation.isPending || sendMutation.isPending}
            title="New chat"
            aria-label="New chat"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-surface-border text-ink-muted transition hover:border-accent/40 hover:bg-accent/5 hover:text-accent disabled:opacity-50"
          >
            <NewChatIcon />
          </button>
        )}
      </div>

      {(needsIndex || indexMutation.isError || startSessionMutation.isError) && (
        <div className="shrink-0 space-y-2 border-b border-surface-border px-5 py-4">
          {needsIndex && (
            <button
              type="button"
              onClick={() => indexMutation.mutate()}
              disabled={indexMutation.isPending}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {indexMutation.isPending ? "Indexing…" : "Index document for chat"}
            </button>
          )}
          {(indexMutation.error || startSessionMutation.error) && (
            <p className="text-sm text-red-600">
              {(indexMutation.error ?? startSessionMutation.error)?.message}
            </p>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col">
        {!sessionId && indexed && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-10 text-center">
            <p className="max-w-md text-sm text-ink-muted">
              Start a conversation to ask about deadlines, evaluation criteria,
              compliance forms, and technical requirements.
            </p>
            <button
              type="button"
              onClick={() => startSessionMutation.mutate()}
              disabled={startSessionMutation.isPending}
              className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {startSessionMutation.isPending ? "Starting…" : "Start conversation"}
            </button>
          </div>
        )}

        {ready && (
          <>
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-5">
              {sessionQuery.isLoading && (
                <p className="text-sm text-ink-muted">Loading messages…</p>
              )}

              {!sessionQuery.isLoading && messages.length === 0 && (
                <div className="flex flex-1 flex-col items-center justify-center gap-5 py-6">
                  <p className="text-center text-sm font-medium text-ink">
                    Try a question
                  </p>
                  <div className="flex w-full flex-wrap justify-center gap-2">
                    {SUGGESTED_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => sendSuggested(prompt)}
                        disabled={sendMutation.isPending}
                        className="rounded-full border border-surface-border bg-surface-muted/80 px-3 py-1.5 text-left text-xs text-ink transition hover:border-accent/40 hover:bg-accent/5 hover:text-accent disabled:opacity-50"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}

              {sendMutation.isPending && (
                <div className="flex justify-start">
                  <div className="rounded-xl border border-surface-border bg-surface-muted/60 px-4 py-3 text-sm text-ink-muted">
                    Thinking…
                  </div>
                </div>
              )}

              {sendMutation.isError && (
                <p className="text-sm text-red-600">{sendMutation.error.message}</p>
              )}
              <div ref={bottomRef} />
            </div>

            {showFollowUps && (
              <div className="shrink-0 border-t border-surface-border bg-surface-muted/20 px-5 py-3">
                <p className="mb-2 text-xs font-medium text-ink-muted">
                  Related follow-ups
                </p>
                <div className="flex flex-wrap gap-2">
                  {followUpQuestions.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => sendSuggested(prompt)}
                      disabled={sendMutation.isPending}
                      className="rounded-full border border-surface-border bg-surface px-3 py-1.5 text-left text-xs text-ink transition hover:border-accent/40 hover:bg-accent/5 hover:text-accent disabled:opacity-50"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <form
              onSubmit={handleSubmit}
              className="shrink-0 border-t border-surface-border bg-surface-muted/30 px-5 py-4"
            >
              <div className="flex gap-3">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about requirements, deadlines, evaluation…"
                  className="min-w-0 flex-1 rounded-lg border border-surface-border bg-surface px-4 py-3 text-sm outline-none ring-accent focus:ring-2"
                  disabled={sendMutation.isPending}
                />
                <button
                  type="submit"
                  disabled={!input.trim() || sendMutation.isPending}
                  className="shrink-0 rounded-lg bg-accent px-5 py-3 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
                >
                  Send
                </button>
              </div>
            </form>
          </>
        )}
      </div>

      {indexQuery.isError && (
        <p className="shrink-0 px-5 py-3 text-sm text-red-600">
          {(indexQuery.error as Error).message}
        </p>
      )}
    </div>
  );
}
