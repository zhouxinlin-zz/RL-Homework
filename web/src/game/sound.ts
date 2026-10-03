import type { Settings } from "./types";

/** Synthesized local audio, unlocked only by an explicit user gesture. */
class DrivingAudio {
  private context: AudioContext | null = null;
  private master: GainNode | null = null;
  private engine: GainNode | null = null;
  private wind: GainNode | null = null;
  private oscillators: OscillatorNode[] = [];
  private noise: AudioBuffer | null = null;
  private effects = 0.65;
  private enabled = false;
  private musicGain: GainNode | null = null;
  private musicTimer: ReturnType<typeof setTimeout> | null = null;
  private chord = 0;
  unlock() {
    try {
      if (!this.context) {
        const ctx = new AudioContext();
        this.context = ctx;
        this.master = ctx.createGain();
        this.master.gain.value = 0;
        this.master.connect(ctx.destination);
        this.musicGain = ctx.createGain();
        this.musicGain.gain.value = 0;
        this.musicGain.connect(this.master);
        this.engine = ctx.createGain();
        this.engine.gain.value = 0;
        const lowpass = ctx.createBiquadFilter();
        lowpass.type = "lowpass";
        lowpass.frequency.value = 470;
        lowpass.Q.value = 0.65;
        this.engine.connect(lowpass);
        lowpass.connect(this.master);
        for (const harmonic of [1, 2.01, 3.005]) {
          const oscillator = ctx.createOscillator(),
            gain = ctx.createGain();
          oscillator.type = "triangle";
          oscillator.frequency.value = 35 * harmonic;
          gain.gain.value = 0.24 / harmonic;
          oscillator.connect(gain);
          gain.connect(this.engine);
          oscillator.start();
          this.oscillators.push(oscillator);
        }
        this.noise = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
        const samples = this.noise.getChannelData(0);
        let brown = 0;
        for (let i = 0; i < samples.length; i++) {
          brown = (brown + (Math.random() * 2 - 1) * 0.04) / 1.025;
          samples[i] = brown * 3.5;
        }
        const source = ctx.createBufferSource();
        source.buffer = this.noise;
        source.loop = true;
        const filter = ctx.createBiquadFilter();
        filter.type = "highpass";
        filter.frequency.value = 260;
        this.wind = ctx.createGain();
        this.wind.gain.value = 0;
        source.connect(filter);
        filter.connect(this.wind);
        this.wind.connect(this.master);
        source.start();
      }
      void this.context.resume().catch(() => undefined);
    } catch {
      /* Audio unavailable; gameplay remains usable. */
    }
  }
  configure(settings: Settings) {
    this.enabled = settings.sound;
    this.effects = settings.effectsVolume ?? 0.65;
    if (this.master && this.context)
      this.master.gain.setTargetAtTime(
        settings.sound ? (settings.volume ?? 0.65) : 0,
        this.context.currentTime,
        0.06,
      );
  }
  drive(speed: number, playing: boolean, settings: Settings) {
    this.configure(settings);
    if (!this.context || !this.engine || !this.wind) return;
    const time = this.context.currentTime,
      motion = playing && settings.sound;
    const amount = settings.engineVolume ?? 0.55;
    this.engine.gain.setTargetAtTime(
      motion ? amount * (0.23 + speed / 200) : 0,
      time,
      0.15,
    );
    this.wind.gain.setTargetAtTime(
      motion ? amount * Math.pow(Math.max(0, speed) / 120, 2) * 0.55 : 0,
      time,
      0.2,
    );
    const base = 28 + speed * 0.56;
    this.oscillators.forEach((oscillator, i) =>
      oscillator.frequency.setTargetAtTime(
        base * [1, 2.01, 3.005][i],
        time,
        0.18,
      ),
    );
  }
  note(frequency = 440, length = 0.08, type: OscillatorType = "sine") {
    if (!this.enabled || !this.context || !this.master) return;
    const ctx = this.context,
      time = ctx.currentTime;
    const oscillator = ctx.createOscillator(),
      gain = ctx.createGain();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, time);
    gain.gain.setValueAtTime(0.0001, time);
    gain.gain.exponentialRampToValueAtTime(
      Math.max(0.0001, 0.1 * this.effects),
      time + 0.006,
    );
    gain.gain.exponentialRampToValueAtTime(0.0001, time + length);
    oscillator.connect(gain);
    gain.connect(this.master);
    oscillator.start();
    oscillator.stop(time + length + 0.01);
    oscillator.onended = () => {
      oscillator.disconnect();
      gain.disconnect();
    };
  }
  event(kind: "overtake" | "collision" | "finish" | "lane") {
    if (!this.enabled || !this.context || !this.master) return;
    if (kind === "finish") {
      this.note(660, 0.3, "triangle");
      this.note(990, 0.4);
      return;
    }
    if (kind === "lane") {
      this.note(420, 0.035, "triangle");
      return;
    }
    const ctx = this.context,
      time = ctx.currentTime;
    const source = ctx.createBufferSource(),
      gain = ctx.createGain(),
      filter = ctx.createBiquadFilter();
    source.buffer = this.noise;
    filter.type = kind === "collision" ? "lowpass" : "bandpass";
    filter.frequency.setValueAtTime(kind === "collision" ? 900 : 1200, time);
    filter.frequency.exponentialRampToValueAtTime(180, time + 0.4);
    gain.gain.setValueAtTime(
      Math.max(0.0001, this.effects * (kind === "collision" ? 1.3 : 0.8)),
      time,
    );
    gain.gain.exponentialRampToValueAtTime(0.0001, time + 0.6);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(this.master);
    source.start();
    source.stop(time + 0.65);
    source.onended = () => {
      source.disconnect();
      filter.disconnect();
      gain.disconnect();
    };
    if (kind === "collision") this.note(70, 0.4, "triangle");
  }
  music(playing: boolean, settings: Settings) {
    if (!this.context || !this.musicGain) return;
    const audible =
      playing &&
      settings.sound &&
      (settings.musicVolume ?? 0.16) > 0 &&
      !document.hidden;
    this.musicGain.gain.setTargetAtTime(
      audible ? (settings.musicVolume ?? 0.16) : 0,
      this.context.currentTime,
      0.2,
    );
    if (!audible) {
      if (this.musicTimer !== null) clearTimeout(this.musicTimer);
      this.musicTimer = null;
      return;
    }
    if (this.musicTimer !== null) return;
    const schedule = () => {
      const ctx = this.context!;
      const time = ctx.currentTime;
      const base = [110, 130.813, 97.999, 116.541][this.chord++ % 4];
      for (const [index, ratio] of [1, 1.5, 2, 2.5].entries()) {
        const note = ctx.createOscillator(),
          gain = ctx.createGain();
        note.type = "sine";
        note.frequency.value = base * ratio;
        note.detune.value = index % 2 ? 3 : -3;
        gain.gain.setValueAtTime(0.0001, time);
        gain.gain.exponentialRampToValueAtTime(
          0.085 / (1 + index * 0.3),
          time + 0.7,
        );
        gain.gain.exponentialRampToValueAtTime(0.0001, time + 4.1);
        note.connect(gain);
        gain.connect(this.musicGain!);
        note.start();
        note.stop(time + 4.2);
        note.onended = () => {
          note.disconnect();
          gain.disconnect();
        };
      }
      this.musicTimer = setTimeout(schedule, 3300);
    };
    schedule();
  }
  silence() {
    if (!this.context) return;
    this.engine?.gain.setTargetAtTime(0, this.context.currentTime, 0.03);
    this.wind?.gain.setTargetAtTime(0, this.context.currentTime, 0.03);
    this.musicGain?.gain.setTargetAtTime(0, this.context.currentTime, 0.03);
    if (this.musicTimer !== null) clearTimeout(this.musicTimer);
    this.musicTimer = null;
  }
}
export const gameAudio = new DrivingAudio();
export const tone = (
  frequency = 440,
  length = 0.08,
  type: OscillatorType = "sine",
) => gameAudio.note(frequency, length, type);
