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

export type Mode = "human" | "ai" | "duel";
export type Theme = "coast" | "city" | "sunset" | "night";
export type VehicleStyle = "sport" | "touring" | "suv";
export type AILevel = {
  id: string;
  name: string;
  description: string;
  available: boolean;
  policy?: string;
  evaluation?: unknown;
};
export type Track = {
  id: string;
  name: string;
  en: string;
  scenario: string;
  env_version?: string;
  duration: number;
  target_m: number;
  theme: Theme;
  difficulty: number;
  description: string;
  overtakes_target?: number;
  brief?: string;
  objectives?: string[];
};
export type Driver = {
  id: string;
  name: string;
  subtitle: string;
  algorithm: string;
  color: string;
  description: string;
  available: boolean;
  steps: number;
};
export type TrainingRoute = {
  episodes: number;
  crashes: number;
  qualification_rate: number;
  mean_score: number;
  mean_distance_m: number;
  mean_overtakes: number;
};
export type TrainingLevel = {
  policy: string;
  method: string;
  checkpoint_steps: number;
  training_steps?: number;
  algorithm?: string;
  run_id?: string;
  checkpoint_sha256?: string;
  overall: {
    episodes: number;
    crashes: number;
    qualification_rate: number;
    mean_score: number;
  };
  routes: Record<string, TrainingRoute>;
};
export type TrainingCatalog = {
  algorithm: string;
  evaluation: string;
  levels: Record<string, TrainingLevel>;
  comparison?: {
    id: string;
    algorithm: string;
    method: string;
    checkpoint_steps: number;
    training_steps: number;
    pretrained: boolean;
    overall: TrainingLevel["overall"];
    routes?: TrainingLevel["routes"];
    history: {
      steps: number;
      crashes: number;
      episodes: number;
      qualification_rate: number;
      mean_score: number;
    }[];
  }[];
  improvement?: {
    promoted: boolean;
    algorithm: string;
    before: TrainingLevel["overall"];
    candidate: TrainingLevel["overall"];
  } | null;
  standard_vs_beginner: {
    pairs: number;
    wins: number;
    losses: number;
    draws: number;
  };
  expert_vs_rule: {
    pairs: number;
    wins: number;
    losses: number;
    draws: number;
  };
};
export type Runner = {
  model_info?: { algorithm?: string; method?: string; run_id?: string } | null;
  decision?: {
    kind: "probability" | "q_value";
    values: number[];
    action: number;
  } | null;
  done: boolean;
  crashed: boolean;
  completed?: boolean;
  qualified?: boolean;
  steps: number;
  model_steps: number;
  total_reward: number;
  distance_m: number;
  mean_speed_kmh: number;
  overtakes: number;
  lane_changes: number;
  danger_seconds: number;
  score: number;
  stars: number;
  risk: {
    gap_m: number | null;
    ttc_s: number | null;
    danger: boolean;
    left?: boolean;
    right?: boolean;
  };
  frame: WorldFrame;
};
export type GameSession = Runner & {
  session_id: string;
  mode: Mode;
  track: Track;
  seed: number;
  policy: string | null;
  player_done: boolean;
  rival: Runner | null;
  created?: string;
  outcome?: "win" | "loss" | "draw" | null;
  ai_level?: string;
  vehicle?: VehicleStyle;
  version?: string;
  env_version?: string;
  practice?: boolean;
  events?: {
    type: string;
    time_s: number;
    label?: string;
    actor?: "player" | "rival";
  }[];
};
export type Catalog = {
  version: string;
  tracks: Track[];
  archive_tracks?: Track[];
  drivers: Driver[];
  archive_drivers?: Driver[];
  step_ms: number;
  ai_levels?: AILevel[];
  archive_ai_levels?: AILevel[];
  training?: TrainingCatalog | null;
};
export type RunConfig = {
  mode: Mode;
  track_id: string;
  policy: string;
  seed?: number;
  ai_level?: string | null;
  vehicle?: VehicleStyle;
  practice?: boolean;
};
export type Records = {
  runs: GameSession[];
  best: { track: string; score: number; stars: number }[];
  total_runs: number;
  duels?: {
    played: number;
    wins: number;
    losses: number;
    draws: number;
    by_level: Record<
      string,
      { played: number; wins: number; losses: number; draws: number }
    >;
  };
};
export type Replay = { summary: GameSession; frames: GameSession[] };
export type Settings = {
  sound: boolean;
  guides: boolean;
  trafficPreview?: boolean;
  color: string;
  reducedMotion: boolean;
  volume?: number;
  engineVolume?: number;
  effectsVolume?: number;
  musicVolume?: number;
  vehicle?: VehicleStyle;
};
export type Phase =
  "idle" | "loading" | "countdown" | "running" | "paused" | "finished";
