const API_BASE = (import.meta.env.VITE_API_BASE || window.location.origin).replace(/\/$/, "");

export type SessionType = "scam_demo" | "assistant";
export type SessionLanguage = "hi-IN" | "en-IN";
export type ThreatEvidence = { text: string; category: string };
export type ThreatPayload = {
  risk_level: "low" | "medium" | "high" | "critical";
  risk_score: number;
  confidence: number | null;
  scam_detected: boolean;
  scam_type: string;
  signals: string[];
  evidence: ThreatEvidence[];
  explanation: string;
  recommended_action: "continue_with_caution" | "warn_user" | "end_call";
  warning_message: string;
};

export async function createSession(sessionType: SessionType, language: SessionLanguage = "hi-IN") {
  const response = await fetch(`${API_BASE}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_type: sessionType, language }),
  });
  if (!response.ok) throw new Error(response.status === 429 ? "Too many sessions. Try again shortly." : "Could not create a voice session.");
  return response.json() as Promise<{ session_id: string; session_type: SessionType; token: string; expires_in: number }>;
}

export function socketUrl(sessionId: string): string {
  const url = new URL(`${API_BASE}/ws/sessions/${encodeURIComponent(sessionId)}`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export async function getConfig() {
  const response = await fetch(`${API_BASE}/api/config`);
  if (!response.ok) throw new Error("Backend unavailable.");
  return response.json() as Promise<{
    providers: { provider: string; model: string; configured: boolean }[];
    live_inference_enabled: boolean;
    assistant_enabled: boolean;
    prisma_sample_rate: 8000 | 16000;
    note: string;
  }>;
}
