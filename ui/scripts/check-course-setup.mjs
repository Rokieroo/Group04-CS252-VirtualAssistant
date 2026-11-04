// Run against the default preview: node scripts/check-course-setup.mjs
import { chromium, expect } from '@playwright/test';
const browser = await chromium.launch({channel:'chrome',headless:true});
try {
 for(const viewport of [{width:1440,height:900},{width:390,height:844}]) {
  const page=await browser.newPage({viewport,colorScheme:'light',reducedMotion:'reduce'});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.PREVIEW_URL || 'http://127.0.0.1:5173');
  await expect(page.getByRole('heading',{name:'Course details',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Continue to review'})).toBeDisabled();
  await page.screenshot({path:`../docs/screenshots/56-57/refactor-upload-${viewport.width}.png`,fullPage:true});
  await page.getByRole('button',{name:'Prefer text?'}).click();
  await page.getByRole('textbox',{name:'Syllabus text'}).fill('Sample syllabus');
  await page.getByRole('button',{name:'Continue to review'}).click();
  await expect(page.getByRole('heading',{name:'Review your syllabus',exact:true})).toBeVisible();
  for(const name of ['Tuần & chủ đề','Đánh giá','Giáo trình','Chuẩn đầu ra']) await page.getByRole('tab',{name,exact:true}).click();
  await page.getByRole('button',{name:'tr. 2',exact:true}).first().click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button',{name:'Xác nhận đề cương',exact:true}).click();
  await page.getByRole('button',{name:'Tạo roadmap →',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Learning path by week'})).toBeVisible();
  await page.locator('.core-week').first().click();
  await expect(page.getByRole('region',{name:'Week 1 details'})).toBeVisible();
  await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0)});
  await page.screenshot({path:`../docs/screenshots/56-57/refactor-roadmap-${viewport.width}.png`,fullPage:true});
  await page.getByRole('button',{name:'Xác nhận roadmap',exact:true}).click();
  await expect(page.getByRole('button',{name:'Trở về môn học',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Xem roadmap →',exact:true}).click();
  expect(page.url()).toContain('#roadmap');
  const geometry=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,nav:document.querySelector('.sidebar').getBoundingClientRect().toJSON()}));
  expect(geometry.scroll).toBeLessThanOrEqual(viewport.width);
  if(viewport.width>viewport.height) expect(geometry.nav.width).toBe(240);
  else {expect(geometry.nav.y).toBe(0);expect(geometry.nav.width).toBe(viewport.width)}
  expect(errors).toEqual([]);
  console.log(`${viewport.width}×${viewport.height}: default app, review tabs, source dialog, approval, navigation and overflow passed`);
  await page.close();
 }
} finally {await browser.close()}
