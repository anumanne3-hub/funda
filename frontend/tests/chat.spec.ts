import { test, expect } from "@playwright/test";

test("help explains API calls and database columns", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Open help" }).click();
  await expect(
    page.getByRole("heading", { name: "API details" }),
  ).toBeVisible();
  await expect(
    page.getByText("Request data and purpose").first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "DB details" }).click();
  await expect(page.getByRole("heading", { name: "DB details" })).toBeVisible();
  await expect(
    page.getByRole("columnheader", { name: "Generated from" }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to chat" }).click();
  await expect(page.getByRole("button", { name: "Open help" })).toBeVisible();
});

test("chat survives reload and stays isolated between browser sessions", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Funda");
  await expect(page.locator(".header-brand > span:first-child")).toHaveText(
    "Funda",
  );
  await expect(page.locator(".header-account")).toHaveText("Guest");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await expect(page.locator(".profile-dropdown")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.locator(".profile-dropdown")).toHaveCount(0);
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
  await expect(page.locator(".header-brand > span:first-child")).toHaveText(
    "Funda",
  );
  await expect(page.locator(".header-account")).toHaveText("Guest");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await page
    .locator(".profile-dropdown")
    .getByRole("button", { name: "Log in" })
    .click();
  await expect(page.getByLabel("Email")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Log in" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Create account" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(
    page.getByRole("button", { name: "Menu", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  const box = await page.getByLabel("Message", { exact: true }).boundingBox();
  await expect(page.getByLabel("Choose conversation")).toBeVisible();
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  await expect(
    page.getByLabel("Choose conversation").locator("option"),
  ).toHaveCount(2);
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  await page.setViewportSize({ width: 320, height: 640 });
  await expect(
    page.getByRole("button", { name: "Menu", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(320);
});

test("desktop sidebar uses 40% width and scrolls independently", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1000, height: 600 });
  await page.goto("/");
  const sidebar = page.locator(".sidebar");
  await expect(sidebar).toBeVisible();
  const box = await sidebar.boundingBox();
  expect(box?.width).toBe(400);
  const conversationList = page.locator(".conversation-list");
  await conversationList.evaluate((element) => {
    for (let i = 0; i < 30; i += 1) {
      const item = document.createElement("div");
      item.textContent = `Conversation ${i}`;
      item.style.padding = "12px";
      element.append(item);
    }
    element.scrollTop = element.scrollHeight;
  });
  expect(
    await conversationList.evaluate((element) => element.scrollTop),
  ).toBeGreaterThan(0);
  expect(
    await sidebar.evaluate((element) => getComputedStyle(element).overflowY),
  ).toBe("clip");
  expect(
    await page.locator(".messages").evaluate((element) => element.scrollTop),
  ).toBe(0);
});

test("long chat scrolls messages while header and composer stay visible", async ({
  page,
}) => {
  for (const width of [1000, 390]) {
    await page.setViewportSize({ width, height: 600 });
    await page.goto("/");
    const header = page.locator(".chat-header");
    const composer = page.locator(".composer");
    const messages = page.locator(".messages");
    const headerTop = (await header.boundingBox())!.y;
    const composerTop = (await composer.boundingBox())!.y;
    await page.locator(".message-list").evaluate((element) => {
      const longMessage = document.createElement("div");
      longMessage.style.height = "1800px";
      element.append(longMessage);
    });
    await messages.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    expect(
      await messages.evaluate((element) => element.scrollTop),
    ).toBeGreaterThan(0);
    expect((await header.boundingBox())!.y).toBe(headerTop);
    expect((await composer.boundingBox())!.y).toBe(composerTop);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  }
});

test("account can claim an anonymous chat and organize it", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Connected");
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await page
    .locator(".profile-dropdown")
    .getByRole("button", { name: "Create account" })
    .click();
  const email = `user-${Date.now()}@example.com`;
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("a-long-test-password");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.locator(".header-account")).toHaveText(email);
  await page.getByRole("button", { name: `User menu: ${email}` }).click();
  await expect(
    page
      .locator(".profile-dropdown")
      .getByRole("button", { name: "Log out", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
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
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await page
    .locator(".profile-dropdown")
    .getByRole("button", { name: "Create account" })
    .click();
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
  await page.getByRole("button", { name: "Edit", exact: true }).click();
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
