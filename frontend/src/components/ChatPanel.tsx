"use client";

import { useState, useRef, useEffect } from "react";
import { sendChat, resumeSimulation } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  hitl_required?: boolean;
  thread_id?: string;
}

export default function ChatPanel() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [threadId, setThreadId] = useState(() => crypto.randomUUID());
  const [pendingHitl, setPendingHitl] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const userId = "default_user";

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

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
          user_id: userId,
          thread_id: threadId,
        });
        const reply: Message = {
          role: "assistant",
          content: res.message,
          hitl_required: res.hitl_required,
          thread_id: res.thread_id,
        };
        setMessages((prev) => [...prev, reply]);

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
              <div className="text-sm font-bold">AI Assistant</div>
              <div className="text-[10px] opacity-80">
                {pendingHitl ? "Waiting for your input..." : "Ask me about your schedule"}
              </div>
            </div>
            <button
              onClick={() => {
                setMessages([]);
                setThreadId(crypto.randomUUID());
                setPendingHitl(null);
              }}
              className="text-[10px] px-2 py-1 rounded bg-blue-500 hover:bg-blue-400 transition-colors"
            >
              Clear
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
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
                  className={`max-w-[80%] px-3 py-2 rounded-xl text-sm ${
                    m.role === "user"
                      ? "bg-blue-600 text-white rounded-br-sm"
                      : "bg-gray-100 text-gray-800 rounded-bl-sm"
                  }`}
                >
                  {m.content}
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

          {/* Input */}
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
        </div>
      )}
    </>
  );
}
