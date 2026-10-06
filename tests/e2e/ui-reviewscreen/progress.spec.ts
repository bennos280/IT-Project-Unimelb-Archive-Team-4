// Dashboard tests use local fixtures; no backend is needed or modified.
import { test, expect } from '@playwright/test';
test('searches bundles and clears an empty result', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name:'All survey bundles'})).toBeVisible();
  await page.getByLabel('Search bundles').fill('216417');
  await expect(page.locator('.progress-table tbody tr')).toHaveCount(1);
  await page.getByLabel('Search bundles').fill('missing');
  await expect(page.getByText('No bundles match your filters.')).toBeVisible();
  await page.getByRole('button',{name:'Clear filters'}).click();
  await expect(page.locator('.progress-table tbody tr')).toHaveCount(1);
});
test('disables pagination for one bundle and filters by status', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Next',exact:true})).toBeDisabled();
  await page.getByLabel('Status',{exact:true}).selectOption('Reviewed');
  await expect(page.getByText('No bundles match your filters.')).toBeVisible();
  await page.getByLabel('Status',{exact:true}).selectOption('Ready to review');
  await expect(page.getByRole('button',{name:'216417',exact:true})).toBeVisible();
});
test('opens bundle pages with matching review targets', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'216417',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Bundle Number · 216417'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Review',exact:true}).nth(1)).toHaveAttribute('href','/?survey=216417&page=216417_p001');
  await page.getByRole('button',{name:'Back to all bundles'}).click();
  await expect(page.getByRole('heading',{name:'All survey bundles'})).toBeVisible();
});
test('Import is plain text and Export opens US12 directly', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Import',exact:true})).toHaveCount(0);
  await expect(page.getByText('Import',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Export',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Export',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Export JSON',exact:true})).toBeEnabled();
});

// Follow each Review action into the real US7 interface with isolated API responses.
for (const [label, pageId, type] of [["Pg 1", "216412/p4", "main"], ["Pg 2", "216417_p001", "notes"], ["Pg 3", "216417_p002", "coded"]]) {
  test(`${label} opens its matching US7 page`, async ({page}) => {
    await page.route('**/api/**', route => {
      const path = new URL(route.request().url()).pathname;
      if (path.includes('/survey/')) return route.fulfill({json: {id:'216417', title:'Survey', pages: [
        {id:pageId, type, imageUrl:'/missing-test-scan.jpg', flags:[], fields:[{id:'test',label:'Test field',group:'Test',value:'value'}]},
      ]}});
      return route.fulfill({json: path.endsWith('/reviewers') ? [] : {reviews:{},revisions:{}}});
    });
    await page.goto('/');
    await page.getByRole('button',{name:'216417',exact:true}).click();
    const row = page.locator('.progress-table tbody tr').filter({has: page.getByRole('cell',{name:label,exact:true})});
    await expect(row.getByRole('link',{name:label,exact:true})).toHaveCount(0);
    await row.getByRole('link',{name:'Review',exact:true}).click();
    await expect(page.locator('.page-heading h2')).toContainText(pageId);
    await expect(page.getByRole('heading',{name:'Transcript Review'})).toBeVisible();
  });
}

for (const width of [936, 640, 375]) {
  test(`page table keeps actions visible at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:900});
    await page.goto('/');
    await page.getByRole('button',{name:'216417',exact:true}).click();
    await expect(page.getByRole('columnheader',{name:'Flags',exact:true})).toBeVisible();
    await expect(page.getByRole('columnheader',{name:'Survey ID',exact:true})).toHaveCount(0);
    await expect(page.getByRole('cell',{name:'5 need checking',exact:true})).toBeVisible();
    for (const link of await page.getByRole('link',{name:'Review',exact:true}).all()) {
      const box = await link.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
    }
    expect(await page.locator('.progress-table-wrap').evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  });
}
