"""Run the real page-side code against isolated fixtures, never real Threads."""
from pathlib import Path
import base64
import json
import tempfile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
PHOTO = base64.b64encode((ROOT/'assets/comment.jpg').read_bytes()).decode()
TEXT = 'Việc onl uy tín kiếm thêm vài cốc trà sữa mỗi ngày 🧋💗'
URL = 'https://www.threads.com/@seeker/post/SOURCE1'
HTML = '''<!doctype html><meta charset="utf-8"><style>body{font:16px sans-serif}article{padding:16px;border:1px solid #ddd;margin:8px}img{width:120px;height:183px}#dialog{display:none;padding:20px}[contenteditable]{min-height:35px}</style>
<nav><a href="/@owner" aria-label="Profile">Profile</a></nav>
<article><a href="/@seeker">seeker</a><a href="/@seeker/post/SOURCE1">now</a><p>Mình đang TÌM VIỆC ONLINE!</p><button aria-label="Reply" onclick="document.querySelector('#dialog').style.display='block'">Reply</button></article>
<div id="dialog" role="dialog"><div id="editor" role="textbox" contenteditable="true"></div><input type="file" accept="image/*"><img id="preview" style="display:none"><button id="send">Đăng</button></div>
<script>
let sends=0;document.querySelector('input').addEventListener('change', e=>{let img=document.querySelector('#preview');img.src=URL.createObjectURL(e.target.files[0]);img.style.display='block';});
document.querySelector('#send').onclick=()=>{sends++;let a=document.createElement('article');let author=document.createElement('a');author.href='/@owner';author.textContent='owner';a.append(author);let link=document.createElement('a');link.href='/@owner/post/REPLY1';link.textContent='now';a.append(link);let text=document.createElement('p');text.textContent=document.querySelector('#editor').innerText;a.append(text);let img=document.createElement('img');img.src=document.querySelector('#preview').src;a.append(img);document.body.append(a);document.querySelector('#dialog').style.display='none';};
</script>'''

def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1280,'height':1200})
        # Every request is fulfilled locally; no real website receives a comment.
        context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html',body=HTML))
        page=context.new_page()
        def reset():
            page.goto(URL);page.add_script_tag(content=(ROOT/'page.js').read_text())
        def task(action,args):
            return page.evaluate('([action,args])=>threadsPageTask(action,args)',[action,args])
        args={'postUrl':URL,'username':'owner','text':TEXT,'image':PHOTO}
        reset()
        assert task('prepare',args)['prepared']
        assert page.locator('#editor').inner_text()==TEXT
        assert page.eval_on_selector('input','el=>el.files[0].size')==(ROOT/'assets/comment.jpg').stat().st_size
        assert task('submit',args)['clicked']
        assert task('proof',args)['replyUrl'].endswith('/@owner/post/REPLY1')
        assert page.evaluate('sends')==1
        try:task('prepare',args)
        except Exception:pass
        else:raise AssertionError('duplicate reply was not blocked')
        assert page.evaluate('sends')==1
        print('PASS: exact content + original image + one submit + verified reply + duplicate prevention')
        reset()
        try:task('prepare',{**args,'username':'wrong_account'})
        except Exception:pass
        else:raise AssertionError('wrong account was not blocked')
        assert page.evaluate('sends')==0
        print('PASS: wrong signed-in account stops before submitting')
        reset();page.eval_on_selector('input','el=>el.remove()')
        try:task('prepare',args)
        except Exception:pass
        else:raise AssertionError('missing image input was not blocked')
        assert page.evaluate('sends')==0
        print('PASS: unknown attachment UI stops without posting')
        reset();page.goto('https://www.threads.com/search?q=t%C3%ACm%20vi%E1%BB%87c%20online');page.add_script_tag(content=(ROOT/'page.js').read_text())
        result=task('collect',{'query':'tìm việc online','username':'owner'})
        assert len(result['posts'])==1 and result['posts'][0]['url']==URL
        print('PASS: keyword search extracts only the matching source post')
        context.close();browser.close()

if __name__=='__main__':main()
