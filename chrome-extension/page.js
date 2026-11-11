/* Runs only in the Threads tab; contains no API, password or cookie access. */
async function threadsPageTask(action, args = {}) {
  const normal = s => String(s || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; };
  const hosts = new Set(['threads.com', 'www.threads.com', 'threads.net', 'www.threads.net']);
  const post = href => { try { const u = new URL(href, location.href); const m = u.pathname.match(/^\/@([\w.]+)\/post\/([\w-]+)\/?$/); return u.protocol === 'https:' && hosts.has(u.hostname) && m ? {url: location.origin + u.pathname.replace(/\/$/, ''), author: m[1], code: m[2]} : null; } catch { return null; } };
  const keywordMatch = text => ['tim viec online', 'cong viec online', 'job online'].some(q => (' ' + normal(text) + ' ').includes(' ' + q + ' '));
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const wait = async (fn, ms = 12000) => { const end = Date.now() + ms; do { guard(); const value = fn(); if (value) return value; await pause(300); } while (Date.now() < end); throw new Error('Giao diện không khớp hoặc chưa tải xong. Đã dừng, không tự thử gửi lại.'); };
  function guard() {
    if (!hosts.has(location.hostname) || location.protocol !== 'https:') throw new Error('Chỉ chạy trên trang Threads HTTPS.');
    const text = normal(document.body.innerText);
    if (document.querySelector('input[type=password], iframe[src*="captcha"], [data-sitekey]') || /try again later|thu lai sau|temporarily blocked|tam thoi bi chan|confirm you are human|xac nhan ban la con nguoi/.test(text)) throw new Error('Threads yêu cầu đăng nhập/xác minh hoặc đang hạn chế thao tác. Đã dừng.');
  }
  const links = el => [...el.querySelectorAll('a[href]')].map(a => ({a, p: post(a.href)})).filter(x => x.p);
  const uniquePaths = el => new Set(links(el).map(x => new URL(x.p.url).pathname));
  const ancestors = el => { const result = []; for (let n = el.parentElement, i = 0; n && n !== document.body && i < 10; i++, n = n.parentElement) result.push(n); return result; };
  const label = el => normal(el.getAttribute('aria-label') || el.getAttribute('title') || el.querySelector('svg[aria-label]')?.getAttribute('aria-label') || el.innerText);
  const replyButtons = el => [...el.querySelectorAll('button,[role=button]')].filter(b => visible(b) && /^(reply|tra loi|binh luan)( \d+)?$/.test(label(b)));
  function editor() {
    const editors = [...document.querySelectorAll('[contenteditable=true][role=textbox],textarea')].filter(visible);
    if (editors.length !== 1) return null;
    const input = editors[0];
    const dialog = input.closest('[role=dialog]') || input.closest('form');
    return dialog && visible(dialog) ? {input, dialog} : null;
  }
  const valueOf = el => el.tagName === 'TEXTAREA' ? el.value : el.innerText;
  function photo(el, inViewport = false) {
    return [...el.querySelectorAll('img')].find(img => {
      const r = img.getBoundingClientRect();
      const parentLink = img.closest('a[href]');
      const isAvatarLink = parentLink && /^\/@[^/]+\/?$/.test(new URL(parentLink.href, location.href).pathname);
      return visible(img) && img.complete && img.naturalWidth >= 120 && img.naturalHeight >= 100 && r.width >= 120 && r.height >= 90 && !/avatar|profile|dai dien|logo/.test(normal(img.alt)) && !isAvatarLink && (!inViewport || (r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth));
    });
  }
  function proof(requireImage = true) {
    const found = [];
    for (const a of document.querySelectorAll('a[href]')) {
      const p = post(a.href);
      if (!p || p.author.toLowerCase() !== args.username.toLowerCase() || p.url === args.postUrl) continue;
      for (const el of ancestors(a)) {
        if (!visible(el) || uniquePaths(el).size !== 1 || !normal(el.innerText).includes(normal(args.text))) continue;
        const author = [...el.querySelectorAll('a[href]')].find(link => { const u = new URL(link.href, location.href); return u.pathname.toLowerCase() === '/@' + args.username.toLowerCase() && normal(link.innerText.replace(/^@/, '')) === normal(args.username) && visible(link); });
        if (author && (!requireImage || photo(el))) found.push({el, url: p.url});
      }
    }
    return found.sort((a,b) => a.el.getBoundingClientRect().height - b.el.getBoundingClientRect().height)[0] || null;
  }
  guard();
  if (action === 'collect') {
    if (location.pathname !== '/search' || normal(new URL(location.href).searchParams.get('q')) !== normal(args.query)) throw new Error('Không đúng trang tìm kiếm đã chọn.');
    const results = new Map();
    for (let step = 0; step < 8 && results.size < 150; step++) {
      guard();
      for (const a of document.querySelectorAll('a[href]')) {
        const p = post(a.href);
        if (!p || p.author.toLowerCase() === args.username.toLowerCase()) continue;
        const el = ancestors(a).find(n => visible(n) && uniquePaths(n).size === 1 && keywordMatch(n.innerText) && n.innerText.length < 6000);
        if (!el || /replying to|dang tra loi/.test(normal(el.innerText))) continue;
        results.set(p.url, {...p, text: el.innerText.slice(0, 1000)});
      }
      window.scrollBy(0, innerHeight * 0.8); await pause(650);
    }
    return {posts: [...results.values()]};
  }
  const current = post(location.href);
  if (!current || (current.url !== args.postUrl && action !== 'proof')) throw new Error('Tab đã chuyển sang bài khác. Đã dừng.');
  if (action === 'prepare') {
    const accountLinks = [...document.querySelectorAll('a[href]')].filter(a => visible(a) && /^(profile|trang ca nhan|ho so)$/.test(label(a)));
    if (accountLinks.length !== 1 || new URL(accountLinks[0].href, location.href).pathname.toLowerCase().replace(/\/$/,'') !== '/@' + args.username.toLowerCase()) throw new Error('Không xác minh được tài khoản đang đăng nhập khớp tên bạn nhập. Chưa gửi.');
    if (proof(false)) throw new Error('Đã thấy bình luận cùng nội dung từ tài khoản của bạn. Không đăng lại.');
    if (editor()) throw new Error('Đang có khung soạn thảo mở. Hãy đóng bản nháp trước khi chạy.');
    const roots = [...document.querySelectorAll('a[href]')].filter(a => post(a.href)?.url === args.postUrl).flatMap(ancestors);
    const root = roots.filter(el => visible(el) && uniquePaths(el).size === 1 && keywordMatch(el.innerText) && replyButtons(el).length === 1).sort((a,b) => a.getBoundingClientRect().height - b.getBoundingClientRect().height)[0];
    if (!root) throw new Error('Không xác định được bài tìm việc và nút Trả lời. Đã dừng.');
    replyButtons(root)[0].click();
    const ed = await wait(editor);
    if (valueOf(ed.input).trim()) throw new Error('Khung trả lời có sẵn nội dung. Không ghi đè.');
    ed.input.focus();
    if (ed.input.tagName === 'TEXTAREA') {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(ed.input, args.text);
      ed.input.dispatchEvent(new Event('input', {bubbles:true}));
    } else {
      const selection = getSelection(); const range = document.createRange(); range.selectNodeContents(ed.input); selection.removeAllRanges(); selection.addRange(range);
      document.execCommand('insertText', false, args.text);
    }
    if (normal(valueOf(ed.input)) !== normal(args.text)) throw new Error('Không điền được đúng nội dung; chưa gửi.');
    const files = [...ed.dialog.querySelectorAll('input[type=file]')].filter(el => !el.accept || /image|jpg|jpeg|png/i.test(el.accept));
    if (files.length !== 1) throw new Error('Không xác định được ô đính kèm ảnh trong khung trả lời. Chưa gửi.');
    const bytes = Uint8Array.from(atob(args.image), c => c.charCodeAt(0));
    const transfer = new DataTransfer(); transfer.items.add(new File([bytes], 'comment-qr.jpg', {type:'image/jpeg'}));
    files[0].files = transfer.files; files[0].dispatchEvent(new Event('change', {bubbles:true}));
    await wait(() => photo(ed.dialog), 18000);
    await wait(() => [...ed.dialog.querySelectorAll('button,[role=button]')].filter(b => visible(b) && /^(post|dang|reply|tra loi)$/.test(label(b)) && !b.disabled && b.getAttribute('aria-disabled') !== 'true').length === 1, 18000);
    return {prepared:true};
  }
  if (action === 'submit') {
    const ed = editor();
    if (!ed || normal(valueOf(ed.input)) !== normal(args.text) || !photo(ed.dialog)) throw new Error('Bản nháp hoặc ảnh không khớp. Chưa gửi.');
    const buttons = [...ed.dialog.querySelectorAll('button,[role=button]')].filter(b => visible(b) && /^(post|dang|reply|tra loi)$/.test(label(b)) && !b.disabled && b.getAttribute('aria-disabled') !== 'true');
    if (buttons.length !== 1) throw new Error('Không xác định được duy nhất nút gửi. Chưa gửi.');
    buttons[0].click(); return {clicked:true};
  }
  if (action === 'proof') {
    const result = await wait(() => proof(true), 18000);
    result.el.scrollIntoView({block:'center', behavior:'instant'}); await pause(300);
    const textVisible = result.el.getBoundingClientRect();
    if (!photo(result.el, true) || textVisible.top < 0 || textVisible.bottom > innerHeight) throw new Error('Bình luận và ảnh chưa nằm trọn trong màn hình. Cần kiểm tra/chụp thủ công, không đăng lại.');
    return {replyUrl: result.url, verified:true};
  }
  throw new Error('Thao tác không được hỗ trợ.');
}
if (typeof module !== 'undefined') module.exports = {threadsPageTask};
