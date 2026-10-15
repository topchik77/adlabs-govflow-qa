import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const evidenceDirectory = process.env.EVIDENCE_DIR || "../../reports";
const password =
  process.env.DEMO_PASSWORD ||
  readFileSync(new URL("../../../.env", import.meta.url), "utf8")
    .match(/^DEMO_PASSWORD=(.+)$/m)![1]
    .trim();

async function login(page: Page, username: string) {
  await page
    .getByRole("combobox", { name: "Учётная запись", exact: true })
    .selectOption(username);
  await page.getByLabel("Пароль локального стенда").fill(password);
  await page.getByRole("button", { name: "Войти в пространство" }).click();
  await expect(page.locator(".login-overlay")).toHaveCount(0);
}
async function changeRole(page: Page, username: string) {
  await page
    .getByRole("button", { name: "Закрыть карточку", exact: true })
    .click();
  await page.locator(".profile").click();
  await login(page, username);
}

test("UI: applicant → reviewer → officer, attachments and audit", async ({
  page,
}) => {
  const title = `UI E2E · ${Date.now()}`;
  await page.goto("/");
  await login(page, "applicant.a");
  await page
    .getByRole("button", { name: "Создать заявление", exact: true })
    .click();
  await page.getByLabel("Название", { exact: true }).fill(title);
  await page
    .getByLabel("Описание", { exact: true })
    .fill("Синтетическое разрешение для проверки полного UI-процесса.");
  await page
    .locator(".modal")
    .getByRole("button", { name: "Создать черновик", exact: true })
    .click();
  const drawer = page.getByRole("dialog", { name: "Карточка заявления" });
  await expect(drawer).toBeVisible();
  await drawer.locator("input[type=file]").setInputFiles({
    name: "ui-synthetic.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.7\nSYNTHETIC UI FIXTURE\n%%EOF"),
  });
  await expect(
    drawer.getByText("ui-synthetic.pdf", { exact: true }),
  ).toBeVisible();
  await drawer
    .getByRole("button", { name: "Подготовить к подписанию" })
    .click();
  await drawer
    .getByRole("button", { name: "Подписать учебной подписью" })
    .click();
  await expect(
    drawer.getByRole("button", { name: "Отправить заявление" }),
  ).toBeVisible();
  // A 202 can be followed by a legitimate SUBMITTED snapshot before the
  // background transition finishes. Force that ordering independently of CPU.
  const applicationId = await drawer.locator(".drawer-id code").textContent();
  const acceptedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/applications/${applicationId}/submit`) &&
      response.status() === 202,
  );
  let servedPendingSnapshot = false;
  await page.route(`**/api/v1/applications/${applicationId}`, async (route) => {
    if (route.request().method() !== "GET" || servedPendingSnapshot) {
      await route.continue();
      return;
    }
    const accepted = await (await acceptedResponse).json();
    const response = await route.fetch();
    const document = await response.json();
    servedPendingSnapshot = true;
    await route.fulfill({
      response,
      json: {
        ...document,
        business_status: accepted.business_status,
        processing_status: accepted.processing_status,
        version: accepted.version,
      },
    });
  });
  await drawer.getByRole("button", { name: "Отправить заявление" }).click();
  await expect(drawer.locator(".drawer-meta")).toContainText("Отправлено");
  await expect(drawer.locator(".drawer-meta")).toContainText("На рассмотрении");
  await changeRole(page, "reviewer.a");
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await drawer
    .getByLabel("Основание решения")
    .fill(
      "Данные проверены. Синтетический документ соответствует требованиям.",
    );
  await drawer.getByRole("button", { name: "Одобрить заявление" }).click();
  await expect(drawer.locator(".drawer-meta")).toContainText("Подпись решения");
  await changeRole(page, "officer.a");
  await page.getByRole("button", { name: new RegExp(title) }).click();
  await drawer
    .getByRole("button", { name: "Подписать итоговое решение" })
    .click();
  await expect(drawer.getByText("Процесс успешно завершён")).toBeVisible();
  await drawer.getByRole("button", { name: /^Аудит/ }).click();
  await expect(drawer.locator(".timeline-event")).toHaveCount(10);
  await page.screenshot({
    path: `${evidenceDirectory}/ui-completed.png`,
    fullPage: true,
  });
  await drawer.getByRole("button", { name: "Закрыть карточку" }).click();
  await page.screenshot({ path: `${evidenceDirectory}/desktop.png`, fullPage: true });
});

test("mobile layout and live search empty state", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await login(page, "applicant.b");
  await expect(
    page.getByRole("heading", { name: "Мои заявления", exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Поиск заявлений")
    .fill("no-matching-synthetic-application");
  await expect(
    page.getByRole("heading", { name: "Ничего не найдено" }),
  ).toBeVisible();
  const widths = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    viewport: innerWidth,
  }));
  expect(widths.doc).toBeLessThanOrEqual(widths.viewport);
  await page.screenshot({ path: `${evidenceDirectory}/mobile.png`, fullPage: true });
});

test("QA observer sees real monitor and cannot browse applications", async ({
  page,
}) => {
  await page.goto("/");
  await login(page, "qa_observer.a");
  await expect(
    page.getByRole("heading", { name: "Качество под наблюдением" }),
  ).toBeVisible();
  await expect(
    page.getByText("local-reference", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Мои заявления" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Очередь рассмотрения" }),
  ).toBeDisabled();
  await page.screenshot({ path: `${evidenceDirectory}/monitor.png`, fullPage: true });
});
