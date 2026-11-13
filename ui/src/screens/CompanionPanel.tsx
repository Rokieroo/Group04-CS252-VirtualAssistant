import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatReply, Message } from "../api";
import { call } from "../api/backend";
import { explain } from "../app/text";
import { Button, Drawer, Field, Loading, Notice } from "../ui/kit";

const moods = [
  ["neutral", "Bình thường"],
  ["happy", "Vui"],
  ["stressed", "Căng thẳng"],
  ["tired", "Mệt"],
] as const;

/** The study companion: a chat about how studying is going. It never changes the schedule itself. */
export function CompanionPanel({ onClose }: { onClose: () => void }) {
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [text, setText] = useState("");
  const [mood, setMood] = useState<string>("neutral");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let current = true;
    call<Message[]>("/ai/messages").then(
      (list) => current && setMessages(list),
      (e) => {
        if (!current) return;
        setError(explain(e));
        setMessages([]);
      },
    );
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => end.current?.scrollIntoView?.({ block: "nearest" }), [messages?.length]);

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    try {
      const reply = await call<ChatReply>("/ai/chat", {
        method: "POST",
        body: JSON.stringify({ message, mood }),
      });
      setOffline(reply.provider === "offline");
      setText("");
      setMessages(await call<Message[]>("/ai/messages"));
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      title="Bạn học"
      onClose={onClose}
      footer={
        <form className="chat-form" onSubmit={send}>
          <Field label="Hôm nay bạn thấy thế nào?">
            <select value={mood} onChange={(event) => setMood(event.target.value)}>
              {moods.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Tin nhắn">
            <textarea
              data-autofocus
              rows={3}
              maxLength={4000}
              required
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary" disabled={busy || !text.trim()}>
            {busy ? "Đang gửi…" : "Gửi"}
          </Button>
        </form>
      }
    >
      {messages === null ? (
        <Loading>Đang tải cuộc trò chuyện…</Loading>
      ) : (
        <div className="chat" role="log" aria-label="Cuộc trò chuyện với bạn học" aria-live="polite">
          {messages.length === 0 && (
            <p className="muted">Kể cho bạn học nghe việc học hôm nay ra sao, hoặc hỏi nên học gì tiếp.</p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`bubble bubble-${m.role}`}>
              <span className="sr-only">{m.role === "user" ? "Bạn: " : "Pathly: "}</span>
              <p className="pre">{m.content}</p>
            </div>
          ))}
          <div ref={end} />
        </div>
      )}
      {offline && (
        <Notice>Dịch vụ AI đang không dùng được, nên bạn học trả lời ở chế độ ngoại tuyến.</Notice>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </Drawer>
  );
}
