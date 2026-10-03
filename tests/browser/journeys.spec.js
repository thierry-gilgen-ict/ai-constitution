const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;
let fixture;
test.beforeEach(async({page,request})=>{
  fixture=await (await request.get('/test/fixture')).json();
  await page.goto('/#'+fixture.token);
  await expect(page.locator('#login')).not.toBeVisible();
  await expect(page.locator('#connection')).toContainText('Connected');
});
const navigate=async(page,name)=>page.locator('.nav[data-page="'+name+'"]').click();

test('update available notification opens release details',async({page})=>{
  await expect(page.locator('#release-badge')).toBeVisible();
  await page.locator('#release-badge').click();
  await expect(page.locator('#updates-content')).toContainText('99.0.0');
  await expect(page.getByRole('button',{name:'Download and verify update'})).toBeVisible();
  await page.getByText('Release changes',{exact:true}).click();
  await expect(page.locator('.release-notes')).toContainText('Synthetic demonstration');
});

test('project discovery previews then enrolls without losing instructions',async({page})=>{
  await navigate(page,'projects'); await page.getByRole('button',{name:'Bring my projects',exact:true}).click();
  await page.locator('#discover-roots').fill(fixture.search_root);
  await page.getByRole('button',{name:'Find repositories',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText('demo-web');
  await page.getByRole('button',{name:'Preview enrollment',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText('2 projects ready');
  await page.getByRole('button',{name:'Enroll ready projects',exact:true}).click();
  await expect(page.locator('#sync-content')).toContainText('demo-web');
  await expect(page.locator('#sync-content')).toContainText('Applications / accounts');
});

test('backup and restore previews keep private values out of the UI',async({page})=>{
  await navigate(page,'vault');
  await page.locator('#vault-backup').click();
  await expect(page.locator('#center-dialog-body')).toContainText('1 files');
  await expect(page.locator('body')).not.toContainText('synthetic-fixture');
  await page.getByRole('button',{name:'Create verified backup',exact:true}).click();
  await expect(page.locator('#operation-strip')).toContainText('Complete');
  await expect(page.locator('[data-restore]')).toHaveCount(1);
  await page.locator('[data-restore]').click();
  await page.locator('#restore-destination').fill(fixture.restore);
  await page.getByRole('button',{name:'Preview restore',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText('never overwritten');
});

test('worker onboarding shows package choices and copyable installation steps',async({page})=>{
  await navigate(page,'workers');
  await expect(page.locator('#worker-commands')).toContainText('node --address');
  await expect(page.locator('#worker-commands')).toContainText('pairing --address');
  await expect(page.getByRole('button',{name:'Copy command'}).first()).toBeVisible();
  await expect(page.locator('#workers-content')).toContainText('Start a worker automatically at login');
});

test('demonstration: capture baseline and start a synthetic local session',async({page})=>{
  await navigate(page,'architectures');
  await page.locator('#template-capture').click();
  await page.locator('#capture-project').fill(fixture.project);
  await page.locator('#capture-id').fill('demo-captured');
  await page.getByRole('button',{name:'Inspect project',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText('nextjs');
  await page.getByRole('button',{name:'Open in template editor',exact:true}).click();
  await expect(page.locator('#template-id')).toHaveValue('demo-captured');
  await page.locator('#template-project').fill(fixture.second);
  await page.locator('#template-project-name').fill('demo-api');
  await page.locator('#template-apply-preview').click();
  await expect(page.locator('#studio-preview-body')).toContainText('revision');
  await page.locator('#studio-preview-confirm').click();
  await navigate(page,'projects');
  await page.locator('[data-project-launch][data-client="codex"]').first().click();
  await expect(page.locator('#notice')).toContainText('Synthetic local session');
});

test('keyboard navigation and accessible control labels',async({page})=>{
  await navigate(page,'updates');
  await page.locator('#update-check').focus(); await page.keyboard.press('Tab');
  await expect(page.locator('#update-auto')).toBeFocused();
  const results=await new AxeBuilder({page}).include('#updates').withTags(['wcag2a','wcag2aa']).analyze();
  expect(results.violations).toEqual([]);
});
