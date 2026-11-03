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

test("account can claim an anonymous chat and organize it", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Email").fill(`user-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("a-long-test-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("button", { name: "Claim anonymous chats" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Claim anonymous chats" }).click();
  page.once("dialog", (dialog) => void dialog.accept("Research"));
  await page.getByRole("button", { name: "+ New project" }).click();
  await expect(page.getByRole("option", { name: "Research" })).toHaveCount(2);
});

test("account can edit, restore, regenerate and rate a reply", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByLabel("Email").fill(`editor-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("a-long-test-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("button", { name: "Claim anonymous chats" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByLabel("Message", { exact: true }).fill("Original prompt");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await expect(page.locator(".message.assistant p")).toContainText(
    "Mock assistant:",
  );
  await expect(page.getByLabel("Streaming response")).toHaveCount(0);
  page.once("dialog", (dialog) => void dialog.accept("Edited prompt"));
  await page.getByRole("button", { name: "Edit" }).click();
  await expect(page.locator(".message.user p")).toHaveText("Edited prompt");
  await page.getByRole("button", { name: "Versions" }).click();
  await page.getByRole("button", { name: "Restore v1" }).click();
  await expect(page.locator(".message.user p")).toHaveText("Original prompt");
  const regenerated = page.waitForResponse(
    (response) =>
      response.url().includes("/regenerate") && response.status() === 200,
  );
  await page.getByRole("button", { name: "Regenerate" }).click();
  await regenerated;
  await expect(page.getByRole("button", { name: "Regenerate" })).toBeEnabled();
  await page
    .getByRole("button", { name: "Helpful answer", exact: true })
    .click();
  await expect(page.locator(".error-banner")).toHaveCount(0);
});
