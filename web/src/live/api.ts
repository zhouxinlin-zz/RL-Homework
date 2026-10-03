import type { DrivingMode, DrivingSession, Policy, Scenario } from "./types";

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(body.detail ?? `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function createSession(
  mode: DrivingMode,
  scenario: Scenario,
  policy: Policy,
  seed?: number,
): Promise<DrivingSession> {
  return json<DrivingSession>(
    await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        scenario,
        policy: mode === "ai" ? policy : null,
        seed,
      }),
    }),
  );
}

export async function stepSession(
  sessionId: string,
  action?: number,
): Promise<DrivingSession> {
  return json<DrivingSession>(
    await fetch(`/api/sessions/${sessionId}/step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }),
  );
}

export async function closeSession(sessionId: string): Promise<void> {
  await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
}
