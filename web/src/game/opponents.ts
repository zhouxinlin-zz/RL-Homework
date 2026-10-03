// Names describe the opponent in the game. Algorithm identities remain in training records.
export function opponentName(policy: string | null, level?: string | null): string {
  const levels: Record<string, string> = { beginner: "入门", standard: "标准", expert: "高手" };
  if (level && levels[level]) return levels[level];
  return ({ v3_beginner: "入门", v3_standard: "标准", v3_expert: "高手",
    v3_ppo: "均衡型", v3_dqn: "基础型", v3_a2c: "进取型" } as Record<string, string>)[policy ?? ""] ?? "电脑";
}
