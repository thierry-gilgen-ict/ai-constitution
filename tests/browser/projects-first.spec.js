const {test,expect}=require('@playwright/test');
const AxeBuilder=require('@axe-core/playwright').default;
async function open(page){await page.goto('/#fixture');await expect(page.locator('#home')).toBeVisible();}

test('six destinations, history and 320px menu remain accessible',async({page})=>{
  await open(page);await expect(page.locator('[data-section]')).toHaveCount(6);
  await page.locator('[data-section="projects"]').click();await expect(page).toHaveURL(/view=project-list/);
  await page.goBack();await expect(page.locator('#home')).toBeVisible();
  await page.setViewportSize({width:320,height:740});
  await page.locator('#menu-toggle').click();await page.locator('[data-section="settings"]').click();
  await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded','false');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.locator('#menu-toggle').click();await page.keyboard.press('Escape');
  await expect(page.locator('#menu-toggle')).toHaveAttribute('aria-expanded','false');
  const result=await new AxeBuilder({page}).include('.topbar').include('#section-tabs').withTags(['wcag2a','wcag2aa']).analyze();
  expect(result.violations).toEqual([]);
});

test('rejected authentication pauses reads and exposes sign-in recovery',async({page})=>{
  let reads=0;await page.route('**/api/status',route=>{reads++;return route.fulfill({status:401,json:{error:'Sign in again'}});});
  await page.goto('/');await expect(page.locator('#connection')).toContainText('Sign-in required');
  await expect(page.locator('#login')).toBeVisible();await page.waitForTimeout(4500);expect(reads).toBe(1);
});

test('missing required asset stops bootstrap with an application error',async({page})=>{
  await page.route('**/experience.js',route=>route.abort());
  await page.goto('/');
  await expect(page.locator('#connection')).toContainText('Application error');
  await expect(page.locator('#notice')).toContainText('Reload');
  await expect(page.locator('#home-add')).toHaveCount(0);
});

test('stalled bootstrap is bounded and unavailable observations remain stale',async({page})=>{
  await open(page);
  await page.route('**/api/status',()=>new Promise(()=>{}));
  await page.locator('#refresh').click();
  await expect(page.locator('#connection')).toContainText('Disconnected',{timeout:11000});
  await expect(page.locator('#notice')).toContainText('eight seconds');
  await expect(page.locator('#home')).toBeVisible();
});

test('hosted onboarding offers three clients without local inference',async({page,request})=>{
  const fixture=await (await request.get('/test/fixture')).json();let inference=0;
  await page.route('**/api/action',route=>{inference++;return route.abort();});
  await open(page);await page.locator('#home-add').click();
  await page.locator('#onboard-project').fill(fixture.second);
  await expect(page.locator('#onboarding-content')).toContainText('Claude Code');
  await page.locator('#onboard-save').click();await page.reload();
  await expect(page.locator('#onboard-project')).toHaveValue(fixture.second);
  await page.locator('#onboard-preview').click();await expect(page.locator('#center-dialog-body')).toContainText('Selected project');
  await page.locator('#center-dialog-apply').click();await expect(page.locator('#project-detail')).toBeVisible();
  expect(inference).toBe(0);expect(page.url()).not.toContain(encodeURIComponent(fixture.second));
});

test('private draft survives navigation and cannot reach active library before publication',async({page,request})=>{
  const headers={Authorization:'Bearer fixture'};
  await open(page);await page.locator('[data-section="instructions"]').click();
  await page.locator('[data-file="constitution.md"]').click();
  const original=await page.locator('#library-editor').inputValue();
  await page.locator('#library-editor').fill(original+'\nBrowser candidate note.\n');
  await page.locator('[data-section="home"]').click();await expect(page.locator('#center-dialog-title')).toHaveText('Keep your edits?');
  await page.locator('#dirty-save').click();await expect(page.locator('#home')).toBeVisible();
  const active=await (await request.get('/api/studio/file?path=constitution.md',{headers})).json();
  expect(active.content).not.toContain('Browser candidate note.');
  const drafts=await (await request.get('/api/ui/drafts',{headers})).json();expect(drafts.files['constitution.md'].content).toContain('Browser candidate note.');
});

test('demo runs only in memory and its CSP blocks controller API connections',async({page,request})=>{
  const response=await request.get('/demo/');expect(response.headers()['content-security-policy']).toContain("connect-src 'none'");
  let calls=0;page.on('request',r=>{if(r.url().includes('/api/'))calls++;});
  await page.route('**/demo.js',async route=>{const original=await route.fetch();await route.fulfill({response:original,body:await original.text()+"\ndocument.getElementById('demo-reset').addEventListener('click',()=>fetch('/api/status').then(()=>{window.cspBlocked=false;}).catch(()=>{window.cspBlocked=true;}));"});});
  await page.goto('/demo/');await expect(page.locator('main')).toContainText('fictional data');
  await page.locator('#demo-reset').click();
  await expect.poll(()=>page.evaluate(()=>window.cspBlocked)).toBe(true);expect(calls).toBeLessThanOrEqual(1); // Browser may emit a blocked request event.
  await expect(page.locator('#demo-status')).toHaveAttribute('role','status');
});
