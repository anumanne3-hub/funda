import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

const external = process.env.SMOKE_BASE_URL;
const backendPython =
  process.platform === "win32"
    ? resolve("../backend/.venv/Scripts/python.exe")
    : "../backend/.venv/bin/python";
export default defineConfig({
  testDir: "./tests",
  timeout: 60000,
  expect: { timeout: external ? 30000 : 5000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: external ?? "http://localhost:5173",
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: external
    ? undefined
    : [
        {
          command: `"${backendPython}" ../scripts/test_server.py`,
          url: "http://localhost:8000/ready",
          timeout: 120000,
          reuseExistingServer: false,
        },
        {
          command: "npm run dev -- --host localhost",
          url: "http://localhost:5173",
          timeout: 120000,
          reuseExistingServer: false,
        },
      ],
});
