const {defineConfig, devices} = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests/browser', timeout: 60000, workers: 1, fullyParallel: false,
  outputDir: '.local/browser-results', reporter: [['list'], ['html', {outputFolder: '.local/browser-report', open:'never'}]],
  use: {baseURL:'http://127.0.0.1:18766', trace:'retain-on-failure', screenshot:'only-on-failure', video:'on'},
  projects:[{name:'chromium', use:{...devices['Desktop Chrome']}},{name:'firefox',use:{...devices['Desktop Firefox'],baseURL:'http://127.0.0.1:18767'}},{name:'webkit',use:{...devices['Desktop Safari'],baseURL:'http://127.0.0.1:18768'}}],
  webServer:[18766,18767,18768].map(port=>({command:'python tests/browser_fixture.py '+port,url:'http://127.0.0.1:'+port+'/',reuseExistingServer:false,timeout:60000})),
});
