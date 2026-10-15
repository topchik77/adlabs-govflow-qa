import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  outputDir: "../../reports/e2e-failures",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  reporter: [
    ["list"],
    ["junit", { outputFile: "../../reports/playwright.xml" }],
  ],
  use: {
    baseURL: process.env.BASE_URL || "http://127.0.0.1:8014",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    screenshot: "only-on-failure",
    trace: "off",
  },
});
