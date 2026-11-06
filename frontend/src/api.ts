const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export type SessionType = "scam_demo" | "assistant";
export type ThreatPayload = {
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  scam_detected: boolean;
  scam_type: string;
  evidence: string[];
  recommended_action: string;
  warning_message: string;
};

export async function createSession(session_type: SessionType) {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_type, language: "hi-en" }),
  });
  if (!response.ok) throw new Error("Could not create a voice session.");
  return response.json() as Promise<{ session_id: string; session_type: SessionType }>;
}

export function socketUrl(sessionId: string) {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/ws/sessions/${sessionId}`;
  return url.toString();
}

export async function getConfig() {
  const response = await fetch(`${API_BASE}/api/config`);
  if (!response.ok) throw new Error("Backend unavailable.");
  return response.json();
}
