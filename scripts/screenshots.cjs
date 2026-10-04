/* Capture the real dashboard with isolated synthetic API data, never the live service. */
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {chromium} = require('@playwright/test');
const {fixture, VERSION, NOW} = require('../tests/fixtures/documentation.cjs');
const {entries, chapters, names} = require('./documentation_scenarios.cjs');
const ROOT = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : null;
const output = path.resolve(ROOT, option('--output') || 'docs/assets/screenshots');
const selected = option('--only')?.split(',');
const assets = ['index.html', 'style.css', 'app.js', 'center.js', 'studio.js', 'experience.js', 'workflows.js'];
const inputs = [...assets.map(a => 'local_control/web/' + a), 'VERSION', 'tests/fixtures/documentation.cjs', 'scripts/documentation_scenarios.cjs', 'scripts/documentation_cli.py', 'scripts/screenshots.cjs', 'templates/architecture-components.json', ...['web-product', 'data-dashboard', 'python-api'].map(id => 'templates/architectures/' + id + '.json'), 'constitution.md', 'engineering.md', 'research.md', 'routing.md', 'registry/routes.json'];
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
inputs.push('tests/fixtures/workflows.cjs');
const sourceDigest = hash(Buffer.concat(inputs.flatMap(file => [Buffer.from(file + '\0'), Buffer.from(fs.readFileSync(path.join(ROOT, file),'utf8').replaceAll('\r\n','\n')), Buffer.from('\0')])));
const e = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ready = {setup:'#setup-summary', overview:'#route .route-row', models:'#installed-models', machines:'#machine-list .driver-panel', connect:'#launch-form', architectures:'[data-template="0"]', constitution:'#library-editor', projects:'#bring-projects', accounts:'[data-account-edit]', workers:'#worker-release-download', storage:'#storage-form', updates:'#update-check', insights:'#performance-refresh', vault:'#restic-settings'};
const badge = `DEMONSTRATION DATA · UI ${VERSION}`;
ready.workflows='#workflow-rollout';

function externalCaptures() {
  return [
    ['cursor-task-picker', 'Cursor task picker and local terminal session', 'docs/local-control.md'],
    ['codex-instructions', 'Codex instruction-loading verification', 'onboarding/project.md'],
    ['grok-bot-setup', 'xAI Grok Bot instruction setup', 'onboarding/bot.md'],
    ['windows-driver-updater', 'Windows native driver update controls', 'docs/driver-maintenance.md'],
    ['macos-driver-updater', 'macOS native Software Update', 'docs/driver-maintenance.md'],
    ['ollama-installer', 'Ollama native installation', 'docs/local-models.md'],
  ].map(([id,title,guide]) => ({id,title,guide,status:'pending',reason:'Requires an actual external application or OS capture. Dashboard fixtures cannot verify that interface.'}));
}

async function main() {
  if (selected?.some(id => !entries.some(v => v.id === id))) throw new Error('Unknown --only screenshot ID');
  fs.mkdirSync(output, {recursive:true});
  const baseline = path.join(ROOT,'docs/assets/screenshots/manifest.json');
  const previous = fs.existsSync(baseline) ? JSON.parse(fs.readFileSync(baseline)) : null;
  const reviewDir = option('--output') ? output : path.join(ROOT,'.local/screenshot-review');
  // Preserve baseline pixels before a default refresh overwrites the published paths.
  const overwritesBaseline = output === path.dirname(baseline);
  if(previous && !selected && overwritesBaseline) {
    const saved = path.join(reviewDir,'baseline'); fs.mkdirSync(saved,{recursive:true});
    for(const old of previous.entries) {
      const source = path.join(ROOT,old.path);
      if(fs.existsSync(source)) fs.copyFileSync(source,path.join(saved,old.id+'.png'));
    }
  }
  const transcripts = JSON.parse(execFileSync(process.env.PYTHON || 'python', ['-X','utf8',path.join(ROOT,'scripts/documentation_cli.py')], {cwd:ROOT,encoding:'utf8'}));
  // Serve only six checked-in web assets. No Python controller, state directory or real API starts.
  const server = http.createServer((req,res) => {
    const name = new URL(req.url, 'http://127.0.0.1').pathname.slice(1) || 'index.html';
    if (!assets.includes(name)) { res.writeHead(404); return res.end(); }
    res.writeHead(200, {'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'text/javascript'});
    res.end(fs.readFileSync(path.join(ROOT,'local_control/web',name)));
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  let browser;
  const captured = [];
  try {
    browser = await chromium.launch();
    for (const entry of entries.filter(v => !selected || selected.includes(v.id))) {
      const context = await browser.newContext({viewport:entry.viewport || {width:1440,height:1000},locale:'en-GB',timezoneId:'UTC',reducedMotion:'reduce',deviceScaleFactor:1,colorScheme:'light'});
      const page = await context.newPage();
      page.setDefaultTimeout(10000);
      const demo = fixture(entry.scenario);
      const errors = [], unexpected = []; let inflight = 0;
      page.on('pageerror', err => errors.push(err.message));
      page.on('dialog', dialog => dialog.accept());
      await page.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== origin) { unexpected.push('Blocked external request: '+url.origin); return route.abort(); }
        if (!url.pathname.startsWith('/api/')) return route.continue();
        inflight++;
        try {
          const value = demo.response(request.url(),request.method(),request.postDataJSON() || {});
          if (value.__status && value.__status !== 401) unexpected.push(value.error);
          const {__status} = value;
          const payload = Array.isArray(value) ? value : {...value};
          if(!Array.isArray(payload)) delete payload.__status;
          await route.fulfill({status:__status || 200,contentType:'application/json',body:JSON.stringify(payload)});
        } catch (err) { errors.push(err.message); await route.fulfill({status:500,body:'{}'}); }
        finally { inflight--; }
      });
      await page.addInitScript(({now}) => {
        const OriginalDate = Date;
        window.Date = class extends OriginalDate { constructor(...values) { super(...(values.length ? values : [now])); } static now() { return now; } };
        // Polls add no coverage here. Every captured action still follows the UI's normal refresh path.
        window.setInterval = () => 0;
      },{now:NOW});
      if (entry.transcript) {
        const t = transcripts[entry.transcript];
        await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#f4f3ed;color:#263b31;font:20px/1.6 system-ui;padding:52px}article{background:#fffefa;border:1px solid #d8ddd0;border-radius:16px;padding:36px;max-width:1180px}h1{font:38px Georgia;margin:0 0 20px}pre{font:19px/1.6 monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#edf0e6;padding:24px;border-radius:10px}.caption{font-size:16px;color:#687460}</style></head><body><article><p class="caption">REAL CLI TRANSCRIPT · ISOLATED TEMPORARY HOME</p><h1>${e(entry.title)}</h1><pre>$ ${e(t.command)}\n\n${e(t.output)}</pre><p class="caption">${e(t.note || 'Actual command output. No client files changed.')}</p><p class="caption">${e(badge)}</p></article></body></html>`);
      } else {
        await page.goto(origin,{waitUntil:'networkidle'});
        await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}'});
        if (entry.scenario === 'login') await page.locator('#login').waitFor({state:'visible'});
        else {
          await page.locator('.nav[data-page="'+entry.page+'"]').click();
          await page.locator(ready[entry.page]).first().waitFor({state:'visible'});
        }
        for (const [action,selector,value] of entry.steps) {
          const locator = page.locator(selector).first();
          if (action === 'click') await locator.click();
          else if (action === 'fill') await locator.fill(value);
          else if (action === 'select') await locator.selectOption(value);
          else if (action === 'scroll') await locator.scrollIntoViewIfNeeded();
          else if (action === 'inner-scroll') await locator.evaluate(el => { el.scrollTop=el.scrollHeight; });
          else throw new Error('Unknown documentation step: '+action);
          await page.waitForTimeout(120);
        }
        await page.waitForFunction(() => !document.fonts || document.fonts.status === 'loaded');
        for (let i=0;i<20&&inflight;i++) await page.waitForTimeout(50);
        await page.waitForTimeout(160);
        // A rendered provenance label travels with element crops as well as complete pages.
        if (entry.scope) {
          await page.locator(entry.scope).first().evaluate((el,label) => {
            const mark=document.createElement('div'); mark.textContent=label;mark.setAttribute('data-docs-marker','');
            mark.style.cssText='font:11px/1.6 system-ui;letter-spacing:1px;color:#536548;background:#edf0e6;padding:8px 12px;margin-top:12px;border-radius:5px';
            if(el.tagName==='DIALOG'&&el.scrollTop) {el.appendChild(mark);el.scrollTop=el.scrollHeight;}
            else el.prepend(mark);
          },badge);
        } else {
          await page.evaluate(label => {const mark=document.createElement('div');mark.textContent=label;mark.style.cssText='position:fixed;bottom:12px;left:12px;z-index:9999;font:10px/1.6 system-ui;letter-spacing:1px;padding:6px 10px;border:1px solid #bac6ac;border-radius:5px;color:#32482c;background:#f6f8ed';document.body.appendChild(mark);},badge);
          if(!entry.steps.some(v=>v[0]==='scroll')) await page.evaluate(() => window.scrollTo(0,0));
        }
        const uiErrors = await page.locator('#center-dialog-error,[data-studio-error],#notice.error').allTextContents();
        if(entry.scenario !== 'login' && uiErrors.some(v=>v.trim())) errors.push(...uiErrors.filter(v=>v.trim()));
      }
      if(errors.length || unexpected.length) throw new Error(entry.id+': '+[...errors,...unexpected].join('; '));
      const file=entry.id+'.png', target=path.join(output,file);
      if(entry.scope) await page.locator(entry.scope).first().screenshot({path:target,animations:'disabled'});
      else await page.screenshot({path:target,animations:'disabled',fullPage:Boolean(entry.overview || entry.fullPage)});
      const bytes=fs.readFileSync(target);
      captured.push({...entry,path:'docs/assets/screenshots/'+file,sha256:hash(bytes),width:bytes.readUInt32BE(16),height:bytes.readUInt32BE(20),bytes:bytes.length});
      console.log('Captured '+entry.id+' ('+Math.round(bytes.length/1024)+' KiB)');
      await context.close();
    }
    if(!selected) {
      const manifest={schema:1,ui_version:VERSION,source_digest:sourceDigest,digest_format:'UTF-8 with LF newlines; filename + NUL + content + NUL',digest_inputs:inputs,capture:{browser:'Chromium',browser_version:browser.version(),platform:process.platform,locale:'en-GB',timezone:'UTC',clock:'2026-10-03T12:00:00Z',default_viewport:{width:1440,height:1000},data:'Synthetic fixture; CLI transcripts use real isolated dry-runs'},pages:names,chapters,entries:captured,external_captures:externalCaptures()};
      fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
      fs.mkdirSync(reviewDir,{recursive:true});
      const review=captured.map(v=>{
        const old=previous?.entries.find(p=>p.id===v.id);
        const changed=!old||old.sha256!==v.sha256;
        const oldPath = old && (overwritesBaseline ? path.join(reviewDir,'baseline',old.id+'.png') : path.join(ROOT,old.path));
        return `<section><h2>${e(v.title)} · ${changed?'Review changed image':'Same bytes'}</h2><p>${e(v.caption)}</p><div class="pair">${old?`<figure><figcaption>Previous baseline · ${e(previous.capture.platform)}</figcaption><img src="${e(path.relative(reviewDir,oldPath).replaceAll('\\','/'))}"></figure>`:''}<figure><figcaption>Captured · ${e(process.platform)}</figcaption><img src="${e(path.relative(reviewDir,path.join(output,v.id+'.png')).replaceAll('\\','/'))}"></figure></div></section>`;
      }).join('');
      fs.writeFileSync(path.join(reviewDir,'review.html'),`<!doctype html><meta charset="utf-8"><title>Documentation screenshot review</title><style>body{font:16px system-ui;margin:32px;background:#f4f3ed;color:#29392e}section{padding:20px;background:white;margin-bottom:24px;border-radius:12px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}figure{margin:0}img{width:100%;height:auto;border:1px solid #dde0d5}figcaption{padding:12px}p{max-width:1000px}</style><h1>Actual UI · synthetic demonstration data</h1><p>Review layout, legibility, content and privacy. Pixel changes are informational: OS fonts and browser builds differ. Current UI ${e(VERSION)}. External app captures are explicitly pending in the manifest.</p>${review}`);
      console.log('Captured '+captured.length+' images; manifest and side-by-side review written.');
    } else console.log('Partial capture: manifest not replaced. Run without --only to refresh the complete set.');
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(err=>{console.error(err);process.exitCode=1;});
