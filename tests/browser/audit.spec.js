const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;
async function open(page){await page.goto('/#fixture');await expect(page.locator('#login')).not.toBeVisible();await page.locator('[data-page="audit"]').click();await expect(page.locator('#audit-scan')).toBeVisible();}

test('health scan is structural and settings remain opt-in',async({page,request})=>{
  await open(page);await page.locator('#audit-scan').click();
  await expect.poll(async()=>{const r=await request.get('/api/audit/overview',{headers:{Authorization:'Bearer fixture'}});return Boolean((await r.json()).latest);}).toBeTruthy();
  await page.locator('[data-audit-tab="inventory"]').click();await expect(page.locator('#audit-view')).toContainText('Scan coverage');
  await page.locator('#audit-settings').click();await expect(page.locator('#audit-enabled')).not.toBeChecked();await expect(page.locator('#audit-sem-enabled')).not.toBeChecked();await expect(page.locator('#audit-mode')).toHaveValue('notify');
  await page.locator('#center-dialog-close').click();
  for(const tab of ['findings','corrections','history','inventory']){await page.locator('[data-audit-tab="'+tab+'"]').click();await expect(page.locator('#audit-view .panel')).toBeVisible();}
  const results=await new AxeBuilder({page}).include('#audit').withTags(['wcag2a','wcag2aa']).analyze();expect(results.violations).toEqual([]);
});

test('health review creates a bounded handoff without running a model',async({page})=>{
  await open(page);await page.locator('[data-audit-tab="findings"]').click();
  await page.locator('#audit-semantic').click();await expect(page.locator('#center-dialog-body')).toContainText('existing login');
  await page.locator('#center-dialog-apply').click();await expect(page.locator('#audit-review-prompt')).toContainText('untrusted DATA');
  await page.locator('#center-dialog-close').click();await page.locator('#audit-worker').click();await expect(page.locator('#center-dialog-body')).toContainText('Pairing alone does not grant');
});
