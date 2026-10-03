import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("real audio starts on a gesture, produces driving output and falls silent when paused or disabled", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const taps: { context: AudioContext; analyser: AnalyserNode }[] = [];
    const originalConnect = AudioNode.prototype.connect;
    // Tap the real master output without replacing, muting, or duplicating its destination.
    AudioNode.prototype.connect = function (...args: unknown[]) {
      const result = Reflect.apply(originalConnect, this, args);
      if (
        args[0] instanceof AudioDestinationNode &&
        !taps.some((tap) => tap.context === this.context)
      ) {
        const analyser = this.context.createAnalyser();
        analyser.fftSize = 2048;
        Reflect.apply(originalConnect, this, [analyser]);
        taps.push({ context: this.context as AudioContext, analyser });
      }
      return result;
    } as typeof AudioNode.prototype.connect;
    Object.assign(window, {
      __laneShiftAudioSignal: () =>
        taps.map(({ context, analyser }) => {
          const samples = new Float32Array(analyser.fftSize);
          analyser.getFloatTimeDomainData(samples);
          const rms = Math.sqrt(
            samples.reduce((sum, sample) => sum + sample * sample, 0) /
              samples.length,
          );
          const peak = samples.reduce(
            (highest, sample) => Math.max(highest, Math.abs(sample)),
            0,
          );
          return { state: context.state, time: context.currentTime, rms, peak };
        }),
    });
  });
  const read = () =>
    page.evaluate(() =>
      (
        window as unknown as {
          __laneShiftAudioSignal: () => {
            state: string;
            time: number;
            rms: number;
            peak: number;
          }[];
        }
      ).__laneShiftAudioSignal(),
    );
  const measurements: Record<string, unknown> = {};
  await page.goto("/");
  await expect(page.locator('.title-start')).toBeEnabled();
  expect(await read()).toEqual([]);
  await page.locator('.title-start').click();
  await expect.poll(async () => (await read())[0]?.state).toBe("running");
  measurements.afterGesture = await read();
  await page.getByRole("button", { name: /驾驶入门/ }).click();
  await expect(page.locator(".driving-buttons")).toBeVisible();
  await expect(page.locator(".countdown-screen")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "暂停游戏", exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () => (await read())[0]?.rms ?? 0)
    .toBeGreaterThan(0.001);
  measurements.driving = await read();
  await page.getByRole("button", { name: "暂停游戏", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "稍作停留" })).toBeVisible();
  await expect
    .poll(async () => (await read())[0]?.rms ?? 1)
    .toBeLessThan(0.00001);
  measurements.paused = await read();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("switch", { name: "游戏音效" }).click();
  await expect(page.getByRole("switch", { name: "游戏音效" })).toHaveAttribute(
    "aria-checked",
    "false",
  );
  await page.getByRole("button", { name: "返回", exact: true }).click();
  const resumedStep = page.waitForResponse(
    (response) => response.url().endsWith("/step") && response.ok(),
  );
  await page.getByRole("button", { name: /继续驾驶/ }).click();
  await resumedStep;
  await expect
    .poll(async () => (await read())[0]?.rms ?? 1)
    .toBeLessThan(0.00001);
  measurements.drivingWithSoundDisabled = await read();
  expect(await read()).toHaveLength(1);
  expect(errors).toEqual([]);
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "返回主菜单", exact: true }).click();
  const report = path.resolve(
    import.meta.dirname,
    "../../artifacts/audio-tests/signal-report.json",
  );
  fs.mkdirSync(path.dirname(report), { recursive: true });
  fs.writeFileSync(
    report,
    JSON.stringify(
      {
        tested_at: new Date().toISOString(),
        browser: "isolated headless Edge",
        check: "Web Audio signal; not a subjective listening assessment",
        measurements,
      },
      null,
      2,
    ),
  );
});
