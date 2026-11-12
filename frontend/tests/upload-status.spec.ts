import { expect, test } from "@playwright/test";

test("paperclip shows upload failure and completed indexing status", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator(".chat-header .status")).toHaveText("Connected", {
    timeout: 30000,
  });
  await page.getByRole("button", { name: "User menu: Guest" }).click();
  await page
    .locator(".profile-dropdown")
    .getByRole("button", { name: "Create account" })
    .click();
  await page.getByLabel("Email").fill(`upload-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill("a-long-test-password");
  await page.getByRole("button", { name: "Continue" }).click();
  const paperclip = page.getByRole("button", { name: "Upload to this chat" });
  await expect(paperclip).toBeVisible();

  await page.route("**/api/v1/conversations/*/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Private document storage failed" }),
      headers: {
        "Access-Control-Allow-Origin": "http://localhost:5173",
        "Access-Control-Allow-Credentials": "true",
      },
    });
  });
  const failedChooser = page.waitForEvent("filechooser");
  await paperclip.click();
  await (
    await failedChooser
  ).setFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Earth"),
  });
  await expect(
    page.getByRole("alert").filter({ hasText: "Failed" }),
  ).toContainText("Private document storage failed");
  await expect(paperclip).not.toHaveClass(/is-active/);

  await page.unroute("**/api/v1/conversations/*/uploads");
  const jobId = "11111111-1111-4111-8111-111111111111";
  const documentId = "22222222-2222-4222-8222-222222222222";
  await page.route("**/api/v1/conversations/*/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        id: jobId,
        document_id: documentId,
        status: "queued",
        attempts: 0,
        error_code: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
      headers: {
        "Access-Control-Allow-Origin": "http://localhost:5173",
        "Access-Control-Allow-Credentials": "true",
      },
    });
  });
  await page.route(`**/api/v1/ingestion-jobs/${jobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: jobId,
        document_id: documentId,
        status: "completed",
        attempts: 1,
        error_code: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
      headers: {
        "Access-Control-Allow-Origin": "http://localhost:5173",
        "Access-Control-Allow-Credentials": "true",
      },
    });
  });
  const readyChooser = page.waitForEvent("filechooser");
  await paperclip.click();
  await (
    await readyChooser
  ).setFiles({
    name: "ready.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Earth"),
  });
  await expect(
    page.getByRole("button", { name: "Document upload in progress" }),
  ).toHaveClass(/is-active/);
  await expect(
    page.getByRole("status").filter({ hasText: "In progress" }),
  ).toBeVisible();
  await expect(page.locator(".upload-toast.completed")).toContainText(
    "ready.md is ready to use",
    { timeout: 15000 },
  );
  await expect(
    page.getByRole("button", { name: "Upload to this chat" }),
  ).not.toHaveClass(/is-active/);
});
