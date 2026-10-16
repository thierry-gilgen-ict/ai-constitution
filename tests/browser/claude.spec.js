const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;

test('Claude settings are explicit and accessible without inference',async({page})=>{
  await page.goto('/#fixture');await expect(page.locator('#login')).not.toBeVisible();
  await page.locator('[data-section="instructions"]').click();await page.locator('[data-page="audit"]').click();await page.locator('#audit-claude').click();
  await expect(page.locator('#center-dialog-body')).toContainText('Claude');
  for(const id of ['claude-monitor','claude-telemetry','claude-share','claude-auto'])await expect(page.locator('#'+id)).not.toBeChecked();
  await expect(page.locator('#claude-key-env')).toHaveValue('');
  const result=await new AxeBuilder({page}).include('#center-dialog').withTags(['wcag2a','wcag2aa']).analyze();
  expect(result.violations).toEqual([]);
  await page.locator('#center-dialog-close').click();
  await page.locator('#audit-settings').click();
  await expect(page.locator('#audit-sem-execution')).toHaveValue('handoff');
  await expect(page.locator('#audit-sem-client option[value="claude-code"]')).toHaveCount(1);
});
