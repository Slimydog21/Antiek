import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";

/**
 * S3 demo panel — fake Chat. Renders a tiny transcript above a real
 * LemonTextarea so the operator can exercise the panel-as-Chat shape
 * before the real ChatInputArea ports onto the panel system in S5.
 */
type Message = { from: "operator" | "agent"; text: string };

const SEED: Message[] = [
  { from: "operator", text: "Why does the gap between groups persist after circuit-depth normalisation?" },
  { from: "agent", text: "Two reasons stand out from the corpus: (1) gate-set choice differs across groups and (2) the Vuletic preprint uses a different decomposition. Both are genuine, not just measurement noise." },
];

export function FakeChat() {
  const [messages, setMessages] = useState<Message[]>(SEED);
  const [draft, setDraft] = useState("");

  const send = (text: string) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { from: "operator", text }]);
    setDraft("");
    // Fake agent reply
    setTimeout(() => {
      setMessages((m) => [
        ...m,
        { from: "agent", text: "Noted. Working on it — this is a demo panel, no substrate behind." },
      ]);
    }, 600);
  };

  return (
    <div className="flex flex-col h-full text-ink dark:text-bright">
      <div className="flex-1 overflow-y-auto p-4 space-y-3 text-[14px]">
        {messages.map((m, i) => (
          <div key={i} className={m.from === "operator" ? "text-right" : ""}>
            <div
              className={
                "inline-block px-3 py-2 rounded-hog max-w-[80%] " +
                (m.from === "operator"
                  ? "bg-sun text-ink"
                  : "bg-ice-3 dark:bg-charcoal-1")
              }
            >
              {m.text}
            </div>
          </div>
        ))}
      </div>
      <div className="border-t-edge border-sun p-3 bg-ice-1 dark:bg-charcoal-1">
        <LemonTextarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onSubmit={send}
          placeholder="Ask a follow-up…  ⌘↵ to send"
          minRows={2}
          maxRows={6}
        />
        <div className="mt-2 flex justify-end">
          <LemonButton variant="primary" size="sm" onClick={() => send(draft)}>
            Send
          </LemonButton>
        </div>
      </div>
    </div>
  );
}

export default FakeChat;
