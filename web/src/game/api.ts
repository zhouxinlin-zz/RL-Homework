import type { Catalog, GameSession, Records, Replay, RunConfig } from "./types";

async function request<T>(
  path: string,
  body?: unknown,
  method = "GET",
): Promise<T> {
  const response = await fetch(`/api/game/${path}`, {
    method,
    keepalive: method === "DELETE",
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "连接失败，请确认游戏服务正在运行。",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  catalog: async () => {
    const catalog = await request<Catalog>("catalog");
    if (
      !catalog.version?.startsWith("3.") ||
      !catalog.tracks?.some(
        (track) => track.id === "weave" && track.env_version === "3.1",
      )
    ) {
      throw new Error(
        "当前连接的是旧版游戏服务。请重新运行 Start-Game.cmd，并使用它新打开的游戏窗口。",
      );
    }
    return catalog;
  },
  start: (config: RunConfig) =>
    request<GameSession>("sessions", config, "POST"),
  step: (id: string, action: number) =>
    request<GameSession>(`sessions/${id}/step`, { action }, "POST"),
  finish: (id: string) =>
    request<GameSession>(`sessions/${id}/finish`, {}, "POST"),
  close: (id: string) => request<void>(`sessions/${id}`, undefined, "DELETE"),
  records: () => request<Records>("records"),
  replay: (id: string) => request<Replay>(`records/${id}/replay`),
  trainingReplay: (track: string) =>
    request<Replay>(`training/replays/${encodeURIComponent(track)}`),
};
