import { test, expect } from "@playwright/test";

test("chat survives reload and stays isolated between browser sessions", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeDisabled();
  await page
    .getByLabel("Message", { exact: true })
    .fill("Milestone persistence check");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message.assistant")).toContainText(/.+/);
  await expect(page.getByLabel("Streaming response")).toHaveCount(0);
  const answer = await page.locator(".message.assistant p").innerText();
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Connected");
  await expect(page.locator(".message.assistant p")).toHaveText(answer);
  await expect(page.locator(".message.user")).toHaveCount(1);
  const other = await browser.newContext();
  const second = await other.newPage();
  await second.goto(process.env.SMOKE_BASE_URL ?? "http://localhost:5173");
  await expect(second.getByRole("status")).toHaveText("Connected");
  await expect(second.locator(".message")).toHaveCount(0);
  await other.close();
});

test("reload during a stream reuses its original request", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page
    .getByLabel("Message", { exact: true })
    .fill("Recover this " + "word ".repeat(80));
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Connected");
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await expect(page.getByLabel("Streaming response")).toHaveCount(0, {
    timeout: 55000,
  });
  await expect(page.locator(".message.user")).toHaveCount(1);
});

test("mobile composer stays within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  const box = await page.getByLabel("Message", { exact: true }).boundingBox();
  await expect(page.getByLabel("Choose conversation")).toBeVisible();
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(
    page.getByLabel("Choose conversation").locator("option"),
  ).toHaveCount(2);
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
});
