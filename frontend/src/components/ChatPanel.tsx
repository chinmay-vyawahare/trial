"use client";

import { useState, useRef, useEffect } from "react";
import { sendChat, resumeSimulation, getChatHistory, getUserThreads, getThreadMessages, deleteThread, deleteUserHistory, createThread } from "@/lib/api";
import type { ChatAction, ChatHistoryUser, ChatThread, ChatThreadSummary } from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  hitl_required?: boolean;
  thread_id?: string;
  actions?: ChatAction[];
}

interface Props {
  userId: string;
  onActions?: (actions: ChatAction[]) => void;
}

type HistoryView = "users" | "threads" | "messages";

export default function ChatPanel({ userId, onActions }: Props) {
  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [threadId, setThreadId] = useState("");
  const [pendingHitl, setPendingHitl] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const historyScrollRef = useRef<HTMLDivElement>(null);
  const effectiveUserId = userId || "default_user";

  // History state
  const [historyView, setHistoryView] = useState<HistoryView>("users");
  const [historyUsers, setHistoryUsers] = useState<ChatHistoryUser[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [userThreads, setUserThreads] = useState<ChatThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [selectedThread, setSelectedThread] = useState<ChatThread | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);

  // Create a new thread via the API
  async function newThread() {
    try {
      const res = await createThread(effectiveUserId);
      setThreadId(res.thread_id);
    } catch {
      // Fallback to client-side UUID if API fails
      setThreadId(crypto.randomUUID());
    }
    setMessages([]);
    setPendingHitl(null);
  }

  // Create initial thread on mount
  useEffect(() => {
    newThread();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll chat messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages, sending]);

  // Auto-scroll history thread messages to bottom
  useEffect(() => {
    if (historyScrollRef.current && selectedThread) {
      historyScrollRef.current.scrollTo({ top: historyScrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [selectedThread]);

  async function loadAllHistory() {
    setHistoryLoading(true);
    try {
      const data = await getChatHistory();
      setHistoryUsers(data);
    } catch (e) {
      console.error("Failed to load chat history:", e);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function loadUserThreads(uid: string) {
    setThreadsLoading(true);
    setSelectedUserId(uid);
    setHistoryView("threads");
    try {
      const threads = await getUserThreads(uid);
      setUserThreads(threads);
    } catch (e) {
      console.error("Failed to load threads:", e);
      setUserThreads([]);
    } finally {
      setThreadsLoading(false);
    }
  }

  async function loadThreadMessages(uid: string, tid: string) {
    setThreadLoading(true);
    setHistoryView("messages");
    try {
      const thread = await getThreadMessages(uid, tid);
      setSelectedThread(thread);
    } catch (e) {
      console.error("Failed to load thread messages:", e);
      setSelectedThread(null);
    } finally {
      setThreadLoading(false);
    }
  }

  function handleOpenHistory() {
    setShowHistory(true);
    setSelectedThread(null);
    // Skip users list — go directly to the current user's threads
    loadUserThreads(effectiveUserId);
  }

  function handleBackToChat() {
    setShowHistory(false);
    setHistoryView("users");
    setSelectedUserId(null);
    setSelectedThread(null);
  }

  function handleHistoryBack() {
    if (historyView === "messages") {
      setHistoryView("threads");
      setSelectedThread(null);
    } else if (historyView === "threads") {
      setHistoryView("users");
      setSelectedUserId(null);
      setUserThreads([]);
    }
  }

  async function handleDeleteThread(e: React.MouseEvent, uid: string, tid: string) {
    e.stopPropagation();
    try {
      await deleteThread(uid, tid);
      if (selectedThread?.thread_id === tid) {
        setSelectedThread(null);
        setHistoryView("threads");
      }
      setUserThreads((prev) => prev.filter((t) => t.thread_id !== tid));
    } catch (err) {
      console.error("Failed to delete thread:", err);
    }
  }

  async function handleDeleteAllThreads() {
    if (!selectedUserId) return;
    try {
      await deleteUserHistory(selectedUserId);
      setUserThreads([]);
      // Also update the users list
      setHistoryUsers((prev) => prev.filter((u) => u.user_id !== selectedUserId));
    } catch (err) {
      console.error("Failed to delete all threads:", err);
    }
  }

  function handleContinueThread(thread: ChatThread) {
    const loadedMessages: Message[] = thread.messages.map((m) => {
      let content = m.content;
      if (m.role === "assistant") {
        try {
          const parsed = JSON.parse(m.content);
          content = parsed.message || m.content;
        } catch {
          // Keep raw content
        }
      }
      return { role: m.role as "user" | "assistant", content };
    });
    setMessages(loadedMessages);
    setThreadId(thread.thread_id);
    handleBackToChat();
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    try {
      if (pendingHitl) {
        const result = await resumeSimulation({
          thread_id: pendingHitl,
          clarification: text,
        });
        setPendingHitl(null);
        const reply: Message = {
          role: "assistant",
          content: (result as Record<string, string>).message || JSON.stringify(result),
        };
        setMessages((prev) => [...prev, reply]);
      } else {
        const res = await sendChat({
          message: text,
          user_id: effectiveUserId,
          thread_id: threadId,
        });
        const reply: Message = {
          role: "assistant",
          content: res.message,
          hitl_required: res.hitl_required,
          thread_id: res.thread_id,
          actions: res.actions,
        };
        setMessages((prev) => [...prev, reply]);

        if (res.actions && res.actions.length > 0 && onActions) {
          onActions(res.actions);
        }

        if (res.hitl_required && res.thread_id) {
          setPendingHitl(res.thread_id);
        }
        if (res.thread_id) {
          setThreadId(res.thread_id);
        }
      }
    } catch (e) {
      const errMsg: Message = {
        role: "assistant",
        content: `Error: ${e instanceof Error ? e.message : "Something went wrong"}`,
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setSending(false);
    }
  }

  function formatTime(dateStr: string | null) {
    if (!dateStr) return "";
    return new Date(dateStr).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  const historyTitle =
    historyView === "messages"
      ? "Thread Messages"
      : historyView === "threads"
      ? `Threads — ${selectedUserId}`
      : "Chat History";

  const historySubtitle =
    historyView === "messages" && selectedThread
      ? `${selectedThread.messages.length} messages`
      : historyView === "threads"
      ? `${userThreads.length} thread${userThreads.length !== 1 ? "s" : ""}`
      : "All users";

  return (
    <>
      {/* Toggle button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full bg-blue-600 text-white shadow-lg flex items-center justify-center hover:bg-blue-700 transition-colors"
        title="AI Assistant"
      >
        {open ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-20 right-5 z-50 w-96 h-[500px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 bg-blue-600 text-white flex items-center justify-between flex-shrink-0">
            <div>
              <div className="text-sm font-bold">
                {showHistory ? historyTitle : "AI Assistant"}
              </div>
              <div className="text-[10px] opacity-80">
                {showHistory
                  ? historySubtitle
                  : pendingHitl
                  ? "Waiting for your input..."
                  : "Ask me about your schedule"}
              </div>
            </div>
            <div className="flex gap-1">
              {!showHistory && (
                <>
                  <button
                    onClick={newThread}
                    className="w-6 h-6 flex items-center justify-center rounded bg-blue-500 hover:bg-blue-400 transition-colors text-white text-sm font-bold"
                    title="New thread"
                  >
                    +
                  </button>
                  <button
                    onClick={handleOpenHistory}
                    className="text-[10px] px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 transition-colors"
                    title="View chat history"
                  >
                    History
                  </button>
                </>
              )}
              {showHistory && (
                <div className="flex gap-1">
                  {historyView === "threads" && userThreads.length > 0 && (
                    <button
                      onClick={handleDeleteAllThreads}
                      className="text-[10px] px-2 py-1 rounded bg-red-500 hover:bg-red-400 transition-colors"
                      title="Delete all threads for this user"
                    >
                      Delete All
                    </button>
                  )}
                  {historyView !== "users" && (
                    <button
                      onClick={handleHistoryBack}
                      className="text-[10px] px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 transition-colors"
                    >
                      Back
                    </button>
                  )}
                  <button
                    onClick={handleBackToChat}
                    className="text-[10px] px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 transition-colors"
                  >
                    Chat
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ── History: Users list ── */}
          {showHistory && historyView === "users" && (
            <div className="flex-1 min-h-0 overflow-y-auto scroll-smooth chat-scroll">
              {historyLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : historyUsers.length === 0 ? (
                <div className="text-center text-xs text-gray-400 mt-12">
                  No chat history found.
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {historyUsers.map((u) => (
                    <button
                      key={u.user_id}
                      onClick={() => loadUserThreads(u.user_id)}
                      className="w-full px-4 py-3 text-left hover:bg-blue-50 transition-colors flex items-center justify-between"
                    >
                      <div>
                        <div className="text-sm font-medium text-gray-800">{u.user_id}</div>
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          {u.threads.length} thread{u.threads.length !== 1 ? "s" : ""}
                        </div>
                      </div>
                      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── History: Threads list for a user ── */}
          {showHistory && historyView === "threads" && (
            <div className="flex-1 min-h-0 overflow-y-auto scroll-smooth chat-scroll">
              {threadsLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : userThreads.length === 0 ? (
                <div className="text-center text-xs text-gray-400 mt-12">
                  No threads found for this user.
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {userThreads.map((t) => (
                    <button
                      key={t.thread_id}
                      onClick={() => loadThreadMessages(selectedUserId!, t.thread_id)}
                      className="w-full px-3 py-2.5 text-left hover:bg-blue-50/50 transition-colors flex items-center justify-between gap-2"
                    >
                      <div className="min-w-0">
                        <div className="text-xs font-mono text-gray-700 truncate">
                          {t.thread_id.slice(0, 8)}...
                        </div>
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          {t.message_count} msg{t.message_count !== 1 ? "s" : ""} · {formatTime(t.last_message_at)}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <span
                          role="button"
                          tabIndex={0}
                          onClick={(e) => handleDeleteThread(e, selectedUserId!, t.thread_id)}
                          onKeyDown={(e) => { if (e.key === "Enter") handleDeleteThread(e as unknown as React.MouseEvent, selectedUserId!, t.thread_id); }}
                          className="text-gray-300 hover:text-red-500 transition-colors"
                          title="Delete thread"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </span>
                        <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── History: Thread messages ── */}
          {showHistory && historyView === "messages" && (
            <>
              {threadLoading ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : selectedThread ? (
                <>
                  <div ref={historyScrollRef} className="flex-1 min-h-0 overflow-y-auto scroll-smooth chat-scroll p-3 space-y-3">
                    {selectedThread.messages.map((m) => {
                      let displayContent = m.content;
                      if (m.role === "assistant") {
                        try {
                          const parsed = JSON.parse(m.content);
                          displayContent = parsed.message || m.content;
                        } catch {
                          // Keep raw
                        }
                      }
                      return (
                        <div
                          key={m.id}
                          className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                        >
                          <div
                            className={`max-w-[80%] px-3 py-2 rounded-xl text-sm break-words ${
                              m.role === "user"
                                ? "bg-blue-600 text-white rounded-br-sm"
                                : "bg-gray-100 text-gray-800 rounded-bl-sm"
                            }`}
                          >
                            {displayContent}
                            {m.created_at && (
                              <div className={`text-[9px] mt-1 ${m.role === "user" ? "opacity-60" : "text-gray-400"}`}>
                                {formatTime(m.created_at)}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="p-3 border-t border-gray-200 flex-shrink-0 flex gap-2">
                    <button
                      onClick={() => handleContinueThread(selectedThread)}
                      className="flex-1 px-3 py-2 text-xs font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
                    >
                      Continue conversation
                    </button>
                    <button
                      onClick={async () => {
                        if (!selectedUserId || !selectedThread) return;
                        await handleDeleteThread(
                          { stopPropagation: () => {} } as React.MouseEvent,
                          selectedUserId,
                          selectedThread.thread_id,
                        );
                      }}
                      className="px-3 py-2 text-xs font-medium rounded-lg bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 transition-colors"
                      title="Delete this thread"
                    >
                      Delete
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-xs text-gray-400">
                  Thread not found.
                </div>
              )}
            </>
          )}

          {/* ── Active chat view ── */}
          {!showHistory && (
            <>
              <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto scroll-smooth chat-scroll p-3 space-y-3">
                {messages.length === 0 && (
                  <div className="text-center text-xs text-gray-400 mt-8">
                    Start a conversation with the AI assistant.
                  </div>
                )}
                {messages.map((m, i) => (
                  <div
                    key={i}
                    className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] px-3 py-2 rounded-xl text-sm break-words ${
                        m.role === "user"
                          ? "bg-blue-600 text-white rounded-br-sm"
                          : "bg-gray-100 text-gray-800 rounded-bl-sm"
                      }`}
                    >
                      {m.content}
                      {m.actions && m.actions.length > 0 && (
                        <div className="mt-1.5 pt-1.5 border-t border-gray-200/50">
                          {m.actions.map((a, ai) => (
                            <div key={ai} className="text-[10px] text-blue-600 font-mono">
                              {a.method} {a.endpoint}
                            </div>
                          ))}
                        </div>
                      )}
                      {m.hitl_required && (
                        <div className="mt-1 text-[10px] opacity-70 italic">
                          Please provide additional information to continue.
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {sending && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 text-gray-500 px-3 py-2 rounded-xl text-sm rounded-bl-sm">
                      <span className="animate-pulse">Thinking...</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="p-3 border-t border-gray-200 flex-shrink-0">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSend()}
                    placeholder={pendingHitl ? "Provide clarification..." : "Type a message..."}
                    className="flex-1 px-3 py-2 text-sm rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                    disabled={sending}
                  />
                  <button
                    onClick={handleSend}
                    disabled={sending || !input.trim()}
                    className="px-3 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Send
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}
