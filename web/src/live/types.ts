export type DrivingMode = "ai" | "human";
export type Policy = "dqn" | "ppo";
export type Scenario = "light" | "normal" | "dense";

export type Vehicle = {
  id: number;
  x: number;
  y: number;
  heading: number;
  speed: number;
  length: number;
  width: number;
  crashed: boolean;
  kind?: string;
};

export type WorldFrame = {
  step: number;
  time_s: number;
  action: number | null;
  reward: number;
  ego_id: number;
  vehicles: Vehicle[];
  target_speed?: number;
  target_lane?: number;
};

export type DrivingSession = {
  session_id: string;
  mode: DrivingMode;
  policy: Policy | null;
  scenario: Scenario;
  seed: number;
  done: boolean;
  crashed: boolean;
  steps: number;
  total_reward: number;
  mean_speed_kmh: number;
  frame: WorldFrame;
};
