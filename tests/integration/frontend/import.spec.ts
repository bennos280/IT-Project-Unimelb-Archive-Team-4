import { test, expect, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";

// Uploads are intercepted: no requests reach the real backend or data folder.
type Upload = { bundle: string | null; filename: string | null };

const file = (name: string, size = 64) => ({
  name,
  mimeType: name.endsWith(".pdf") ? "application/pdf" : "image/png",
  buffer: Buffer.alloc(size, 1),
});
const picker = (page: Page) => page.locator('input[type="file"]');
const row = (page: Page, name: string) => page.locator("tbody tr", { hasText: name });
const importButton = (page: Page) => page.getByRole("button", { name: "Import files" });

async function mockUploads(page: Page, reply: (upload: Upload) => { status: number; detail?: string }, delay = 0) {
  const uploads: Upload[] = [];
  await page.route("**/api/bundles/upload**", async (route) => {
    const query = new URL(route.request().url()).searchParams;
    const upload = { bundle: query.get("bundle"), filename: query.get("filename") };
    uploads.push(upload);
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    const { status, detail } = reply(upload);
    await route.fulfill({ status, json: detail ? { detail } : { ...upload, size: 64 } });
  });
  return uploads;
}

test("files need an item number, and unsupported, empty or repeated files are not added", async ({ page }) => {
  // Files on disk, so choosing one again is the same file (same name, size and modified time).
  const [onDisk, text, empty] = [["one.pdf", 64], ["notes.txt", 64], ["empty.pdf", 0]].map(([name, size]) => {
    const path = test.info().outputPath(name as string);
    writeFileSync(path, Buffer.alloc(size as number, 1));
    return path;
  });
  await page.goto("/?view=import");
  await expect(page.getByText("No files selected.")).toBeVisible();
  await expect(importButton(page)).toBeDisabled();
  await picker(page).setInputFiles([onDisk, text, empty]);
  await expect(page.getByRole("alert")).toContainText("Not added: notes.txt, empty.pdf");
  await expect(page.locator("tbody tr")).toHaveCount(1);
  const bundle = page.getByLabel("Item number for one.pdf");
  await expect(bundle).toHaveAttribute("aria-invalid", "true");
  await bundle.fill("12a");
  await expect(importButton(page)).toBeDisabled();
  await bundle.fill("216500");
  await expect(bundle).toHaveAttribute("aria-invalid", "false");
  await expect(importButton(page)).toBeEnabled();
  await picker(page).setInputFiles([onDisk]);
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Remove one.pdf" }).click();
  await expect(page.getByText("No files selected.")).toBeVisible();
});

test("each file is sent with its own item number and a refusal shows the server's reason", async ({ page }) => {
  const uploads = await mockUploads(page, ({ filename }) =>
    filename === "taken.pdf" ? { status: 409, detail: "This PDF already exists in item 216412. It has not been uploaded." } : { status: 201 });
  await page.goto("/?view=import");
  await picker(page).setInputFiles([file("taken.pdf"), file("new.pdf")]);
  await page.getByLabel("Item number for taken.pdf").fill("216501");
  await page.getByLabel("Item number for new.pdf").fill(" 216502 ");
  await importButton(page).click();
  await expect(page.getByRole("status")).toHaveText("1 of 2 files uploaded. Transcription has not started.");
  expect(uploads).toEqual([{ bundle: "216501", filename: "taken.pdf" }, { bundle: "216502", filename: "new.pdf" }]);
  await expect(page.getByRole("alert")).toHaveText("taken.pdf: This PDF already exists in item 216412. It has not been uploaded.");
  await expect(row(page, "taken.pdf")).not.toContainText("Uploaded");
  await expect(page.getByLabel("Item number for taken.pdf")).toBeEnabled();
  await expect(row(page, "new.pdf")).toContainText("Uploaded");
  await expect(page.getByLabel("Item number for new.pdf")).toBeDisabled();
});

test("page images of one item share its item number", async ({ page }) => {
  const uploads = await mockUploads(page, () => ({ status: 201 }));
  await page.goto("/?view=import");
  await picker(page).setInputFiles([file("page1.png"), file("page2.png")]);
  await page.getByLabel("Item number for page1.png").fill("216503");
  await page.getByLabel("Item number for page2.png").fill("216503");
  await importButton(page).click();
  await expect(page.getByRole("status")).toHaveText("2 of 2 files uploaded. Transcription has not started.");
  expect(uploads.map((upload) => upload.bundle)).toEqual(["216503", "216503"]);
  await expect(importButton(page)).toBeDisabled();
});

test("controls are locked while an upload is under way", async ({ page }) => {
  await mockUploads(page, () => ({ status: 201 }), 1000);
  await page.goto("/?view=import");
  await picker(page).setInputFiles([file("slow.pdf")]);
  await page.getByLabel("Item number for slow.pdf").fill("216504");
  await importButton(page).click();
  await expect(page.getByRole("status")).toHaveText("Uploading 1 of 1: slow.pdf");
  await expect(page.getByRole("button", { name: "Choose files" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Remove slow.pdf" })).toBeDisabled();
  await expect(page.getByLabel("Item number for slow.pdf")).toBeDisabled();
  await expect(page.getByRole("status")).toHaveText("1 of 1 files uploaded. Transcription has not started.");
});

test("a dropped file is added", async ({ page }) => {
  await page.goto("/?view=import");
  const dropped = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([new Uint8Array([37, 80, 68, 70])], "dropped.pdf", { type: "application/pdf" }));
    return transfer;
  });
  const zone = page.getByTestId("dropzone");
  await zone.dispatchEvent("dragover", { dataTransfer: dropped });
  await expect(zone).toHaveAttribute("data-dragging", "true");
  await zone.dispatchEvent("drop", { dataTransfer: dropped });
  await expect(zone).toHaveAttribute("data-dragging", "false");
  await expect(row(page, "dropped.pdf")).toBeVisible();
});
