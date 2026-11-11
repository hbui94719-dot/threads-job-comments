importScripts('page.js');
const KEY = 'threadsLocalBotV1';
const ALARM = 'threads-local-next';
const QUERIES = ['tìm việc online', 'công việc online', 'job online'];
let working = false;
let cancelRequested = false;
const initial = () => ({active:false, phase:'idle', history:{}, queue:[], count:0, queryIndex:0, log:[], text:'Việc onl uy tín kiếm thêm vài cốc trà sữa mỗi ngày 🧋💗 Đang có sale nên công khá cao áaa, ai muốn tìm hiểu thì ib mình nhaaa 🫶', username:'', goal:1});
const load = async () => (await chrome.storage.local.get(KEY))[KEY] || initial();
async function save(s, message) {
  if (cancelRequested) s.active = false;
  if (message) s.log = [{at:new Date().toISOString(), message}, ...(s.log || [])].slice(0,100);
  await chrome.storage.local.set({[KEY]:s});
}
function isThreads(url) { try { const u = new URL(url); return u.protocol === 'https:' && ['threads.com','www.threads.com','threads.net','www.threads.net'].includes(u.hostname); } catch { return false; } }
function used(s) { const cutoff = Date.now() - 86400000; return Object.values(s.history).filter(e => e.status !== 'captured' || e.at > cutoff).length; }
async function stop(message) {
  const s = await load(); s.active = false; s.phase = 'idle'; await save(s, message); await chrome.alarms.clear(ALARM);
}
async function running() { const s = await load(); if (cancelRequested || !s.active) throw new Error('Đã dừng theo yêu cầu.'); return s; }
async function tabReady(tabId, url) {
  await chrome.tabs.update(tabId, {url});
  for (let i=0;i<35;i++) {
    await running(); const tab = await chrome.tabs.get(tabId);
    if (!isThreads(tab.url)) throw new Error('Tab chuyển sang đăng nhập hoặc trang khác. Đã dừng.');
    if (tab.status === 'complete' && tab.url === url) { await new Promise(r => setTimeout(r, 1200)); return tab; }
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error('Trang chưa tải xong; không tự thử lại.');
}
async function page(tabId, action, args) {
  if (cancelRequested && (action === 'prepare' || action === 'submit')) throw new Error('Đã dừng theo yêu cầu; không nhấn gửi tiếp.');
  const tab = await chrome.tabs.get(tabId);
  if (!isThreads(tab.url)) throw new Error('Không đúng tab Threads.');
  const results = await chrome.scripting.executeScript({target:{tabId}, func:threadsPageTask, args:[action,args]});
  if (results.length !== 1 || !results[0].result) throw new Error('Không nhận được kết quả từ trang. Đã dừng.');
  return results[0].result;
}
async function photoBase64() {
  const r = await fetch(chrome.runtime.getURL('assets/comment.jpg')); if (!r.ok) throw new Error('Thiếu ảnh QR trong tiện ích.');
  const bytes = new Uint8Array(await r.arrayBuffer()); let text = ''; for (const b of bytes) text += String.fromCharCode(b); return btoa(text);
}
async function downloadComplete(data, filename) {
  const id = await chrome.downloads.download({url:data, filename, saveAs:false});
  for (let i=0;i<35;i++) {
    const [item] = await chrome.downloads.search({id});
    if (item?.state === 'complete') return id;
    if (item?.state === 'interrupted') throw new Error('Chrome không lưu được screenshot. Không đăng lại bình luận.');
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error('Chưa xác nhận được screenshot đã lưu. Không đăng lại.');
}
async function tick() {
  if (working) return;
  working = true;
  let postUrl;
  try {
    let s = await load(); if (!s.active) return;
    if (s.phase !== 'idle') throw new Error('Lượt trước bị gián đoạn. Hãy kiểm tra bình luận và bản nháp; tool không tự thử gửi lại.');
    if (s.count >= s.goal || used(s) >= 500) { await stop('Đã đạt số lượng đặt hoặc trần 500 trong 24 giờ.'); return; }
    const tab = await chrome.tabs.get(s.tabId);
    if (!tab.active || !isThreads(tab.url)) throw new Error('Giữ tab Threads được chọn trong cửa sổ Chrome. Đã dừng khi tab khác được chọn.');
    s.phase = 'searching'; await save(s);
    while (!s.queue.length && s.queryIndex < QUERIES.length) {
      const query = QUERIES[s.queryIndex++]; const url = s.origin + '/search?q=' + encodeURIComponent(query);
      await tabReady(s.tabId, url);
      const found = new Map(); let unchanged = 0;
      for (let round = 0; round < 12 && found.size < s.goal-s.count && unchanged < 2; round++) {
        await running();
        const result = await page(s.tabId, 'collect', {query, username:s.username});
        const before = found.size;
        for (const p of result.posts) if (!s.history[p.url]) found.set(p.url,p);
        unchanged = found.size === before ? unchanged+1 : 0;
      }
      s.queue = [...found.values()]; await save(s, `Tìm “${query}”: ${s.queue.length} bài chưa xử lý.`);
    }
    if (!s.queue.length) { await stop('Không tìm thêm được bài phù hợp trong kết quả hiện có. Không chuyển sang bảng tin.'); return; }
    const target = s.queue.shift(); postUrl = target.url;
    await tabReady(s.tabId, postUrl);
    await running();
    s.phase = 'reserved'; s.current = postUrl;
    s.history[postUrl] = {at:Date.now(), status:'reserved'};
    await save(s, 'Đang chuẩn bị: ' + postUrl);
    const args = {postUrl, username:s.username, text:s.text, image:await photoBase64()};
    await page(s.tabId, 'prepare', args);
    await running();
    // Persist before clicking. An unknown result is never automatically retried.
    s.phase = 'submitting'; s.history[postUrl].status = 'uncertain'; await save(s);
    await page(s.tabId, 'submit', {postUrl, username:s.username, text:s.text});
    const proofArgs = {postUrl, username:s.username, text:s.text};
    const proof = await page(s.tabId, 'proof', proofArgs);
    s.phase = 'proof'; s.history[postUrl] = {at:Date.now(), status:'proof_pending', replyUrl:proof.replyUrl}; await save(s);
    const before = await chrome.tabs.get(s.tabId);
    if (!before.active || before.url !== postUrl) throw new Error('Tab đã thay đổi trước lúc chụp. Bình luận đã gửi, không đăng lại.');
    const png = await chrome.tabs.captureVisibleTab(before.windowId, {format:'png'});
    const after = await chrome.tabs.get(s.tabId);
    if (!after.active || after.url !== before.url) throw new Error('Tab thay đổi trong lúc chụp. Cần kiểm tra bình luận đã gửi.');
    const check = await page(s.tabId, 'proof', proofArgs);
    if (check.replyUrl !== proof.replyUrl) throw new Error('Không xác minh được ảnh chụp của đúng bình luận.');
    const file = 'threads-job-comments/' + new Date().toISOString().replace(/[:.]/g,'-') + '.png';
    const downloadId = await downloadComplete(png, file);
    const latest = await load(); s.active = latest.active;
    s.history[postUrl] = {at:Date.now(), status:'captured', replyUrl:proof.replyUrl, file, downloadId}; s.count++; s.phase = 'idle';
    // Keep 10,000 recently processed source posts; unknown results are never discarded.
    const entries = Object.entries(s.history).sort((a,b) => b[1].at-a[1].at);
    s.history = Object.fromEntries(entries.filter(([,e],i) => i < 10000 || e.status !== 'captured'));
    await save(s, `Đã xác nhận ${s.count}/${s.goal}; screenshot: ${file}`);
    if (!s.active || s.count >= s.goal) await stop('Đã dừng. Các ảnh xác nhận nằm trong thư mục Downloads/threads-job-comments.');
  } catch (error) {
    const s = await load(); s.active = false;
    if (postUrl && s.history[postUrl]) s.history[postUrl].error = String(error.message).slice(0,300);
    await save(s, String(error.message).slice(0,400)); await chrome.alarms.clear(ALARM);
  } finally { working = false; }
}
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === ALARM) tick(); });
chrome.runtime.onStartup?.addListener(() => stop('Chrome vừa khởi động lại. Bấm Bắt đầu khi bạn đã kiểm tra tab và tài khoản.'));
chrome.runtime.onInstalled?.addListener(() => stop('Tiện ích vừa được cài/cập nhật. Chưa chạy và chưa gửi bình luận.'));
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  (async () => {
    if (message.action === 'status') return load();
    if (message.action === 'stop') {
      cancelRequested = true; await chrome.alarms.clear(ALARM);
      if (!working) await stop('Bạn đã yêu cầu dừng.');
      const s = await load(); return {...s, active:false};
    }
    if (message.action === 'export') {
      const s = await load(); const json = JSON.stringify(s, null, 2); const encoded = btoa(unescape(encodeURIComponent(json)));
      await chrome.downloads.download({url:'data:application/json;base64,'+encoded, filename:'threads-job-comments/nhat-ky.json', saveAs:true}); return {ok:true};
    }
    if (message.action !== 'start') throw new Error('Thao tác không hợp lệ.');
    const s = await load(); if (s.active || working) throw new Error('Tool đang chạy.');
    if (Object.values(s.history).some(e => e.status === 'proof_pending' || e.status === 'uncertain')) throw new Error('Có bình luận chưa rõ kết quả. Xuất nhật ký và kiểm tra trước khi chạy tiếp; không đăng lại.');
    if (!/^[A-Za-z0-9._]{1,30}$/.test(message.username)) throw new Error('Nhập đúng tên Threads của bạn, bỏ dấu @.');
    if (!Number.isInteger(message.goal) || message.goal < 1 || message.goal > 500) throw new Error('Số lượng phải từ 1 đến 500.');
    if (typeof message.text !== 'string' || !message.text.trim() || [...message.text].length > 500) throw new Error('Nội dung phải từ 1 đến 500 ký tự.');
    const tab = await chrome.tabs.get(message.tabId);
    if (!tab.active || !isThreads(tab.url)) throw new Error('Mở Threads, đăng nhập rồi bấm biểu tượng tiện ích ngay trên tab đó.');
    if (used(s) >= 500) throw new Error('Đã đạt trần 500 hoặc đang có kết quả chưa rõ cần kiểm tra.');
    cancelRequested = false;
    Object.assign(s, {active:true, phase:'idle', queue:[], queryIndex:0, count:0, goal:message.goal, username:message.username, text:message.text.trim(), tabId:tab.id, origin:new URL(tab.url).origin});
    await save(s, `Bắt đầu, tối đa ${s.goal} bình luận. Máy không ngủ và tab Threads phải được chọn.`);
    await chrome.alarms.create(ALARM, {periodInMinutes:1, when:Date.now()+60000});
    setTimeout(tick, 50); return s;
  })().then(sendResponse).catch(error => sendResponse({error:error.message}));
  return true;
});
