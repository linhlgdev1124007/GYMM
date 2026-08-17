const { chromium } = require('@playwright/test');
const { execFileSync } = require('child_process');
(async () => {
  const token = execFileSync('docker', ['compose','exec','-T','app','python','-c', "from server.database import SessionLocal; from server.models import User; from server.security import create_session; db=SessionLocal(); user=db.query(User).filter(User.role=='admin', User.is_active==True).order_by(User.id).first(); print(create_session(db,user)); db.close()"], { cwd: process.cwd(), encoding: 'utf8' }).trim();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.context().addCookies([{ name: 'gym_session', value: token, domain: '127.0.0.1', path: '/', httpOnly: true, sameSite: 'Strict' }]);
  await page.goto('http://127.0.0.1:3333/reports?view=debt&from=2026-08-01&to=2026-08-17', { waitUntil: 'networkidle' });
  await page.screenshot({ path: '.tmp/report-debt.png', fullPage: false });
  const info = await page.evaluate(() => {
    const table = document.querySelector('.report-view .data-table');
    const thead = document.querySelector('.report-view .data-table thead');
    const ths = [...document.querySelectorAll('.report-view .data-table th')].map((th) => ({ text: th.innerText, rect: th.getBoundingClientRect().toJSON(), display: getComputedStyle(th).display, visibility: getComputedStyle(th).visibility, color: getComputedStyle(th).color, bg: getComputedStyle(th).backgroundColor, z: getComputedStyle(th).zIndex }));
    const filter = document.querySelector('.report-filter-bar');
    return { url: location.href, table: table?.getBoundingClientRect().toJSON(), thead: thead?.getBoundingClientRect().toJSON(), filter: filter?.getBoundingClientRect().toJSON(), ths };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
})();
