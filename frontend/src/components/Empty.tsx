import { Network } from "lucide-react";

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty">
      <Network size={32} />
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}
