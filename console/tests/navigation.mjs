// Shared navigation for live smoke tests after moving tool management off the chat surface.
export async function openSettings(page,tab='接入与管理'){
 await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();
 if(tab==='GitHub 链策略'){
  await page.getByRole('tab',{name:'接入与管理',exact:true}).click();await chooseConnection(page,'github');
  const policy=page.locator('.connection-policy');if(!await policy.getAttribute('open'))await policy.locator('summary').click();return;
 }
 await page.getByRole('tab',{name:tab,exact:true}).click();
}
export async function chooseConnection(page,kind){await page.getByLabel('工具接入方式',{exact:true}).selectOption(kind);}
export async function openChat(page){
 await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'Agent 对话',exact:true}).click();
}
// Explicit OrgB test review of synthetic read-only fixtures; no production auto-labeling.
export async function labelLowRiskForTest(page){
 await page.getByLabel('自定义工具版本审阅').waitFor();
 await page.getByLabel('工具审核风险等级').selectOption('LOW');
}
export async function openDetails(page){
 if(!await page.getByLabel('审批与执行详情',{exact:true}).count())await page.getByRole('button',{name:'审批与证据',exact:true}).click();
 await page.getByLabel('审批与执行详情',{exact:true}).waitFor();
}
export async function chooseTask(page,id,{details=false}={}){
 await openChat(page);
 const mobile=page.getByRole('button',{name:'历史任务',exact:true});
 if(await mobile.isVisible()&&await mobile.getAttribute('aria-expanded')==='false')await mobile.click();
 await page.getByLabel('搜索任务').fill('');
 await page.locator('button.task').filter({has:page.locator(`code[title="${id}"]`)}).click();
 if(details)await openDetails(page);
}
