import { useState } from "react";
import { sendMessage } from "../api";

export default function Composer({ onResult }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const message = text.trim();
    if (!message || sending) return;

    setSending(true);
    setText("");
    try {
      const result = await sendMessage(message);
      onResult(message, result, null);
    } catch (err) {
      onResult(message, null, err.message);
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Assign Piyal to the multi-modal RAG chatbot project…"
        className="flex-1 rounded-lg border border-white/10 bg-[#1C1F26] px-4 py-3 text-sm text-[#E8E6E1] placeholder:text-[#5B5F68] outline-none focus:border-[#D4A64A]"
      />
      <button
        type="submit"
        disabled={sending}
        className="rounded-lg bg-[#D4A64A] px-4 py-3 text-sm font-medium text-[#15171B] disabled:opacity-50"
      >
        {sending ? "Sending…" : "Send"}
      </button>
    </form>
  );
}