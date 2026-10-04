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

test('workspace inspector, preparation and toolkit ownership through real APIs',async({page,request})=>{
  const headers={Authorization:'Bearer '+fixture.token};
  const workspace=await (await request.get('/api/workspace',{headers})).json();
  if(!workspace.projects.some(p=>p.project===fixture.project)){
    const body={projects:[{project:fixture.project}]};
    const preview=await (await request.post('/api/workspace/preview',{headers,data:body})).json();
    expect((await request.post('/api/workspace/apply',{headers,data:{...body,plan:preview.plan}})).ok()).toBeTruthy();
  }
  await navigate(page,'workflows');await expect(page.locator('[data-inspect]').first()).toBeVisible();
  await page.locator('[data-inspect]').first().click();await expect(page.locator('#center-dialog-body')).toContainText('client_loading');
  await page.locator('#center-dialog-close').click();await page.locator('[data-prepare]').first().click();
  await expect(page.locator('#prepare-recipe')).toContainText('schema');await page.locator('#center-dialog-apply').click();
  await expect(page.locator('#center-dialog-body')).toContainText('Resume ID');await page.locator('#center-dialog-close').click();
  await page.locator('[data-workflow-tab="toolkits"]').click();await page.locator('#toolkit-new').click();
  await page.locator('#center-dialog-apply').click();await expect(page.locator('#workflows-content')).toContainText('Project quality');
  await page.locator('#toolkit-install').click();await page.locator('[data-kit-select]').check();await page.locator('#center-dialog-apply').click();
  await expect(page.locator('#center-dialog-body')).toContainText('.codex');await page.locator('#center-dialog-apply').click();
  await expect(page.locator('#operation-strip')).toContainText('Complete');
});

test('workspace keyboard palette and opt-in automation remain accessible',async({page})=>{
  await navigate(page,'workflows');await page.keyboard.press('Control+k');
  await expect(page.locator('#workspace-query')).toBeFocused();await page.locator('#workspace-query').fill('Resource');
  await page.locator('#workspace-query').fill('workflows');await expect(page.locator('.palette-result').first()).toBeVisible();
  await page.keyboard.press('ArrowDown');await expect(page.locator('.palette-result').first()).toBeFocused();await page.keyboard.press('Escape');
  await page.locator('[data-workflow-tab="profiles"]').click();await expect(page.locator('#profiles-enabled')).not.toBeChecked();
  await page.locator('#rule-apps').fill('fixture-game.exe');await page.locator('#rule-add').click();
  await expect(page.locator('#rule-summary')).toContainText('fixture-game.exe');
  await expect(page.locator('#profiles-enabled')).not.toBeChecked();
  const results=await new AxeBuilder({page}).include('#workflows').withTags(['wcag2a','wcag2aa']).analyze();expect(results.violations).toEqual([]);
});

test('all workspace sections load and controller listener stays opt-in',async({page})=>{
  await navigate(page,'workflows');
  for(const tab of ['toolkits','controllers','recovery','lab','profiles','projects']){
    await page.locator('[data-workflow-tab="'+tab+'"]').click();await expect(page.locator('#workflows-content .panel').first()).toBeVisible();
    if(tab==='controllers'){
      await page.locator('#fleet-enable').click();await expect(page.locator('#center-dialog-body')).toContainText('private IPv4');await page.locator('#center-dialog-close').click();
    }
  }
  await expect(page.locator('#notice')).not.toContainText('Cannot read properties');
});

test('update available notification opens release details',async({page})=>{
  await expect(page.locator('#release-badge')).toBeVisible();
  await page.locator('#release-badge').click();
  await expect(page.locator('#updates-content')).toContainText('99.0.0');
  await expect(page.getByRole('button',{name:'Download and verify update'})).toBeVisible();
  await page.getByText('Release changes',{exact:true}).click();
  await expect(page.locator('.release-notes')).toContainText('Synthetic demonstration');
});

test('project discovery previews then enrolls without losing instructions',async({page,request})=>{
  const before=await (await request.get('/api/workspace',{headers:{Authorization:'Bearer '+fixture.token}})).json();
  const ready=2-before.projects.filter(p=>[fixture.project,fixture.second].includes(p.project)).length;
  await navigate(page,'projects'); await page.getByRole('button',{name:'Bring my projects',exact:true}).click();
  await page.locator('#discover-roots').fill(fixture.search_root);
  await page.getByRole('button',{name:'Find repositories',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText('demo-web');
  await page.getByRole('button',{name:'Preview enrollment',exact:true}).click();
  await expect(page.locator('#center-dialog-body')).toContainText(ready+' projects ready');
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
