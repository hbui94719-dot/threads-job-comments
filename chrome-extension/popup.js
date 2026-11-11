const $ = id => document.getElementById(id);
let initialized = false;
async function update() {
  const s = await chrome.runtime.sendMessage({action:'status'});
  if (!initialized) { $('username').value=s.username || ''; $('text').value=s.text || ''; $('goal').value=s.goal || 1; initialized=true; }
  $('start').disabled=!!s.active; $('username').disabled=!!s.active; $('text').disabled=!!s.active; $('goal').disabled=!!s.active;
  $('status').textContent=(s.active ? 'Đang chạy' : 'Đang dừng') + ` · ${s.count || 0}/${s.goal || 1} đã gửi và lưu screenshot`;
  $('log').replaceChildren(...(s.log || []).map(e => { const li=document.createElement('li'); li.textContent=new Date(e.at).toLocaleTimeString('vi-VN')+' · '+e.message; return li; }));
}
$('start').addEventListener('click',async()=>{
  $('error').textContent='';
  $('start').disabled=true;
  try {
    const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
    const r=await chrome.runtime.sendMessage({action:'start',tabId:tab.id,username:$('username').value.trim().replace(/^@/,''),text:$('text').value,goal:Number($('goal').value)});
    if(r.error) throw new Error(r.error); await update();
  } catch(e) { $('error').textContent=e.message; $('start').disabled=false; }
});
$('stop').addEventListener('click',async()=>{await chrome.runtime.sendMessage({action:'stop'});await update();});
$('export').addEventListener('click',()=>chrome.runtime.sendMessage({action:'export'}));
update().catch(e=>$('status').textContent=e.message);
setInterval(()=>update().catch(()=>{}),1500);
