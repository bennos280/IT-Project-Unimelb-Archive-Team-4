import { test, expect, type Page } from "@playwright/test";

// The home page's welcome, asking who is working before anything else in a browser, on an intercepted API: nothing reaches the
// real backend. These start with no one working (the other specs start as Ben).
test.use({ storageState: { cookies: [], origins: [] } });

// The people saved, and those added.
async function mock(page: Page, people: { id: number; name: string }[]) {
  const added: string[] = [];
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/reviewers" && route.request().method() === "POST") {
      const { name } = route.request().postDataJSON();
      added.push(name);
      people.push({ id: people.length + 1, name });
      return route.fulfill({ status: 201, json: people.at(-1) });
    }
    if (path === "/api/reviewers") return route.fulfill({ json: people });
    if (path === "/api/collections") return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: `Unexpected test request: ${path}` } });
  });
  return added;
}

const welcome = (page: Page) => page.getByRole("region", { name: "Welcome to PrestCribe" });
const who = (page: Page) => page.getByRole("form", { name: "Who's working?" });

test("a name saved before is chosen from the list, or someone new added; Switch person asks again", async ({ page }) => {
  const added = await mock(page, [{ id: 1, name: "Ben" }, { id: 2, name: "Sandy" }]);
  await page.goto("/");
  const name = who(page).getByLabel("Your name");
  await expect(name.locator("option")).toHaveText(["Choose your name", "Ben", "Sandy", "Someone new…"]);
  await name.selectOption("Someone new…");
  await expect(who(page).getByLabel("New name")).toBeFocused();
  await name.selectOption("Sandy");
  await expect(who(page).getByLabel("New name")).toHaveCount(0);
  await who(page).getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Series", level: 1 })).toBeVisible();
  expect(added).toEqual([]);

  await page.getByRole("button", { name: "Working as Sandy" }).click();
  await page.getByRole("menuitem", { name: "Switch person" }).click();
  await expect(welcome(page)).toBeVisible();
  await expect(page.getByRole("button", { name: /^Working as/ })).toHaveCount(0);
});

test("a name kept from another database isn't this one's, so the welcome asks again", async ({ page }) => {
  await mock(page, [{ id: 1, name: "Sandy" }]);
  await page.addInitScript(() => localStorage.setItem("prestcribe.person", JSON.stringify({ id: 1, name: "Ben" })));
  await page.goto("/");
  await expect(welcome(page)).toBeVisible();
  await expect(who(page).getByLabel("Your name").locator("option")).toHaveText(["Choose your name", "Sandy", "Someone new…"]);
});
