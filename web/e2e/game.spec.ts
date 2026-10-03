import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const shots = path.resolve(import.meta.dirname, "../../artifacts/preview/v3");
fs.mkdirSync(shots, { recursive: true });
async function openSetup(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(
    page.locator('.game-scene[data-rendered="true"] canvas'),
  ).toBeVisible();
  await page.getByRole("button", { name: /选择起始路线/ }).click();
  await expect(page.getByRole("dialog", { name: "赛前准备" })).toBeVisible();
  await expect(page.getByRole("dialog")).not.toContainText(
    /PPO|DQN|A2C|初始化|检查点|入门|标准|其他电脑对手|自由驾驶/,
  );
}

test("an older backend shows recovery instructions instead of an empty game", async ({
  page,
}) => {
  await page.route("**/api/game/catalog", (route) =>
    route.fulfill({
      json: {
        version: "2.0.0",
        tracks: [{ id: "coast" }],
        drivers: [],
        ai_levels: [],
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("旧版游戏服务");
  await expect(page.locator(".title-start")).toBeDisabled();
});

test("one expert contest replaces extra modes and the routes describe the actual itinerary", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".title-start")).toContainText("三关连赛");
  await expect(
    page.locator(
      '.game-scene[data-engine="three"][data-rendered="true"] canvas',
    ),
  ).toBeVisible();
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.join(shots, "01-main-menu.png") });
  await openSetup(page);
  await expect(page.getByLabel("本次赛程").locator("> div")).toHaveCount(1);
  await page.getByRole("button", { name: /更换路线/ }).click();
  await expect(page.locator(".track-tile")).toHaveCount(3);
  await expect(page.getByText("更多路线", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join(shots, "02-challenge-routes.png") });
  await page.getByRole("button", { name: /慢车编队/ }).click();
  await expect(page.getByLabel("本次赛程").locator("> div")).toHaveCount(3);
  await expect(
    page.locator(".ai-levels, .opponent-picker, .mode-tabs"),
  ).toHaveCount(0);
  await page.screenshot({ path: path.join(shots, "03-duel-setup.png") });
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.locator(".title-more summary").click();
  await expect(
    page.getByRole("button", { name: "车库", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await expect(page.getByRole("switch", { name: "周车预览" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("training names the deployed checkpoint and separates it from candidate algorithms", async ({
  page,
}) => {
  await page.goto("/");
  await page.locator(".title-more summary").click();
  await page.getByRole("button", { name: /训练成果/ }).click();
  const catalog = await (await page.request.get("/api/game/catalog")).json();
  const expert = catalog.training.levels.expert;
  const dialog = page.getByRole("dialog", { name: "训练成果" });
  await expect(
    dialog.getByRole("heading", { name: "高手对手 · PPO" }),
  ).toBeVisible();
  await expect(dialog.getByLabel("正式对手检查点")).toContainText(
    expert.checkpoint_steps.toLocaleString("en-US"),
  );
  await expect(dialog.getByLabel("正式对手检查点")).toContainText(
    `${(expert.overall.qualification_rate * 100).toFixed(1)}%`,
  );
  await expect(dialog.locator(".model-card")).toHaveCount(0);
  await expect(dialog.locator(".model-proof")).toContainText(
    `${catalog.training.expert_vs_rule.wins} 胜`,
  );
  await expect(dialog.locator(".model-play")).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: path.join(shots, "04-training-results.png") });
  await page.getByText("训练来源与模型标识", { exact: true }).click();
  await expect(dialog.locator("code")).toContainText(expert.checkpoint_sha256);
  await page.getByRole("button", { name: "PPO / DQN / A2C 对照" }).click();
  await expect(page.locator(".algorithm-results article")).toHaveCount(3);
  await expect(page.locator(".algorithm-comparison")).toContainText(
    "不在正式比赛中轮流接管车辆",
  );
  await expect(page.locator(".model-play")).toBeInViewport({ ratio: 1 });
  await page.screenshot({
    path: path.join(shots, "12-algorithm-comparison.png"),
  });
});

test("three real rounds preserve the checkpoint, paired traffic, verdicts and score after replay", async ({
  page,
}) => {
  test.setTimeout(210000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  let wins = 0,
    losses = 0;
  for (const [index, track] of ["convoy", "weave", "pressure"].entries()) {
    const creation = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/game/sessions") &&
        response.request().method() === "POST",
    );
    await (
      index === 0
        ? page.locator(".title-start")
        : page.getByRole("button", { name: /继续下一段/ })
    ).click();
    const session = await (await creation).json();
    expect(session.track.id).toBe(track);
    expect(session.mode).toBe("duel");
    expect(session.ai_level).toBe("expert");
    expect(session.policy).toBe("v3_expert");
    expect(session.seed).toBe(531124);
    expect(session.frame.vehicles).toEqual(session.rival.frame.vehicles);
    expect(session.rival.model_info.algorithm).toBe("ppo");
    expect(session.rival.model_steps).toBe(175000);
    await expect(page.locator(".countdown-screen")).toHaveCount(0);
    await expect(page.locator(".duel-standing")).toContainText(
      `第 ${index + 1} / 3 段`,
    );
    await page.screenshot({ path: path.join(shots, `3d-${track}.png`) });
    if (index === 0) {
      const action = page.waitForRequest(
        (request) =>
          request.url().endsWith("/step") &&
          request.postDataJSON()?.action === 3,
      );
      await page.keyboard.press("ArrowUp");
      await action;
      await page.getByRole("button", { name: "查看 AI 决策" }).click();
      await expect(page.getByLabel("AI 实时决策")).toContainText("PPO");
      await page.screenshot({ path: path.join(shots, "14-ppo-decision.png") });
      await page.getByRole("button", { name: "收起 AI 决策" }).click();
      await page.screenshot({ path: path.join(shots, "05-live-duel.png") });
      await page.keyboard.press("Escape");
      await expect(
        page.getByRole("dialog", { name: "游戏暂停" }),
      ).toBeVisible();
      await page.getByRole("button", { name: /继续驾驶/ }).click();
    }
    await expect(page.getByRole("dialog", { name: "驾驶结算" })).toBeVisible({
      timeout: session.track.duration * 1000 + 10000,
    });
    const record = await (
      await page.request.get(`/api/game/records/${session.session_id}/replay`)
    ).json();
    expect(record.frames.at(-1).done).toBe(true);
    if (record.summary.outcome === "win") wins++;
    if (record.summary.outcome === "loss") losses++;
    await expect(page.getByLabel("赛程战绩")).toContainText(
      `你 ${wins} : ${losses} 电脑`,
    );
    await expect(page.getByLabel("本局得分")).toContainText(
      record.summary.score.toLocaleString("en-US"),
    );
    await page.screenshot({
      path: path.join(shots, `07-round-${index + 1}-results.png`),
    });
    if (index === 0) {
      const moment = page
        .getByLabel("本局关键时刻")
        .getByRole("button")
        .first();
      await expect(moment).toBeVisible();
      const moments = (await moment.innerText()).match(/([\d.]+) s/)!;
      const seek = Number(moments[1]);
      await moment.click();
      await expect(
        page.getByRole("slider", { name: "回放进度" }),
      ).toBeVisible();
      const value = Number(
        await page.getByRole("slider", { name: "回放进度" }).inputValue(),
      );
      const time = Math.max(
        record.frames[value].frame.time_s,
        record.frames[value].rival.frame.time_s,
      );
      expect(time).toBeGreaterThanOrEqual(Math.max(0, seek - 3.2));
      expect(time).toBeLessThanOrEqual(seek + 1);
      await page.screenshot({ path: path.join(shots, "08-replay.png") });
      await page.getByRole("button", { name: "退出回放" }).click();
      await expect(
        page.getByRole("dialog", { name: "驾驶结算" }),
      ).toBeVisible();
      await expect(page.getByLabel("赛程战绩")).toContainText(
        `你 ${wins} : ${losses} 电脑`,
      );
    }
  }
  await expect(page.getByLabel("赛程战绩")).toContainText("赛程结束");
  await expect(page.getByRole("button", { name: /继续下一段/ })).toHaveCount(0);
  const fresh = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/game/sessions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "换一组车流" }).click();
  const newRoad = await (await fresh).json();
  expect(newRoad.seed).not.toBe(531124);
  expect(newRoad.policy).toBe("v3_expert");
  expect(newRoad.frame.vehicles).toEqual(newRoad.rival.frame.vehicles);
  await page.getByRole("button", { name: "暂停游戏" }).click();
  await page.getByRole("button", { name: "返回主菜单", exact: true }).click();
  expect(errors).toEqual([]);
});

test("the pressure route is a single 55 second expert duel with no easier fallback", async ({
  page,
}) => {
  await openSetup(page);
  const creation = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/game/sessions") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /开始人机对决/ }).click();
  const session = await (await creation).json();
  expect(session.track.id).toBe("pressure");
  expect(session.track.duration).toBe(55);
  expect(session.policy).toBe("v3_expert");
  await expect(page.locator(".countdown-screen")).toHaveCount(0);
  await expect(page.locator(".duel-standing")).not.toContainText("第 1 / 3 段");
  await expect(page.getByLabel("AI 实时决策")).toHaveCount(0);
  await page.getByRole("button", { name: "暂停游戏" }).click();
  await page.getByRole("button", { name: "返回主菜单", exact: true }).click();
});

test("3D assets, all road themes and held controls work at desktop presentation sizes", async ({
  page,
}) => {
  const errors: string[] = [];
  const assets = new Set<string>();
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().includes("/models/")) {
      if (!response.ok())
        errors.push(`Asset ${response.status()}: ${response.url()}`);
      if (response.url().endsWith(".glb")) assets.add(response.url());
    }
  });
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  await expect(
    page.locator('.game-scene[data-engine="three"][data-rendered="true"]'),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "训练成果", exact: true }),
  ).toBeHidden();
  await page.screenshot({ path: path.join(shots, "3d-menu-720.png") });
  for (const [id, title] of [
    ["convoy", "慢车编队"],
    ["weave", "交织车流"],
    ["pressure", "连续高压"],
  ]) {
    await page.getByRole("button", { name: /选择起始路线/ }).click();
    await page.getByRole("button", { name: /更换路线/ }).click();
    await page.getByRole("button", { name: new RegExp(title) }).click();
    await page.getByRole("button", { name: /开始人机对决/ }).click();
    await expect(page.locator(".countdown-screen")).toBeVisible();
    await expect(page.locator(".countdown-screen")).toHaveCount(0);
    await page.keyboard.down("ArrowUp");
    await expect(
      page.getByRole("button", { name: "加速", exact: true }),
    ).toHaveClass(/is-pressed/);
    const throttle = page.waitForRequest(
      (request) =>
        request.url().endsWith("/step") && request.postDataJSON()?.action === 3,
    );
    await throttle;
    await page.keyboard.up("ArrowUp");
    await expect(
      page.getByRole("button", { name: "加速", exact: true }),
    ).not.toHaveClass(/is-pressed/);
    const standing = (await page.locator(".duel-standing").boundingBox())!;
    const rival = (await page.locator(".rival-label").boundingBox())!;
    expect(rival.y).toBeGreaterThanOrEqual(standing.y + standing.height);
    await page.screenshot({ path: path.join(shots, `3d-${id}-720.png`) });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(shots, `3d-${id}.png`) });
    console.log(
      `${id}: ${await page.locator(".game-scene").getAttribute("data-fps")} fps`,
    );
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "游戏暂停" })).toBeVisible();
    await page.getByRole("button", { name: "返回主菜单", exact: true }).click();
    await page.setViewportSize({ width: 1280, height: 720 });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(shots, "01-main-menu.png") });
  expect(assets.size).toBe(7);
  expect(errors).toEqual([]);
});
