import { useState, useCallback } from "react";
import api from "@/utils/api";

export interface Message {
  role: "user" | "assistant";
  content: string;
  source?: string;
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (question: string) => {
      setMessages((prev) => [...prev, { role: "user", content: question }]);
      setLoading(true);

      try {
        const { data: job } = await api.post("/chat/ask", {
          question,
          conversation_id: conversationId,
        });

        if (job.status === "done" && job.answer) {
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: job.answer, source: job.source },
          ]);
          if (job.conversation_id) setConversationId(job.conversation_id);
          return;
        }

        // Poll until done
        const jobId = job.job_id;
        if (job.conversation_id) setConversationId(job.conversation_id);

        await poll(jobId);
      } catch (e: any) {
        const detail = e.response?.data?.detail || "Something went wrong";
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `Error: ${detail}` },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [conversationId]
  );

  const poll = async (jobId: string, attempts = 0) => {
    if (attempts > 60) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Request timed out. Please try again." },
      ]);
      return;
    }
    await new Promise((r) => setTimeout(r, 1500));
    const { data } = await api.get(`/chat/result/${jobId}`);
    if (data.status === "done" || data.status === "error") {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "No response received.",
          source: data.source,
        },
      ]);
    } else {
      await poll(jobId, attempts + 1);
    }
  };

  const reset = () => {
    setMessages([]);
    setConversationId(null);
  };

  return { messages, loading, sendMessage, reset };
}
