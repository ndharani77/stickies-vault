window.Stickies = (() => {
  const API_URL = localStorage.getItem('stickies_api_url') || 'http://127.0.0.1:8000';
  const TOKEN_KEY = 'stickies_access_token';
  const USER_KEY = 'stickies_username';

  function token(){ return localStorage.getItem(TOKEN_KEY) || ''; }
  function user(){ return localStorage.getItem(USER_KEY) || ''; }
  function setSession(data){
    const nextUser = data?.user?.username || '';
    if(nextUser && user() && nextUser !== user()){
      localStorage.removeItem('stickies_vault_notes');
      localStorage.removeItem('stickies_vault_folders_v1');
      localStorage.removeItem('stickies_vault_editor_state_v1');
    }
    if(data?.access_token) localStorage.setItem(TOKEN_KEY, data.access_token);
    if(nextUser) localStorage.setItem(USER_KEY, nextUser);
  }
  function clearSession(){
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem('stickies_unlocked');
  }
  function go(url){
    sessionStorage.setItem('stickies_internal_nav', String(Date.now()));
    location.href = url;
  }
  function loginRequired(){
    if(!token()){ go('../lock_screen/code.html'); return false; }
    return true;
  }
  async function api(path, options={}){
    const headers = new Headers(options.headers || {});
    if(options.body && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
    if(token()) headers.set('Authorization','Bearer ' + token());
    try {
      const res = await fetch(API_URL + path, {...options, headers});
      let data = null;
      try { data = await res.json(); } catch {}
      if(res.status === 401 && path !== '/login' && path !== '/register'){
        clearSession();
        go('../lock_screen/code.html');
        throw new Error(data?.detail || 'Session expired');
      }
      if(!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
      if(path === '/login' && data && data.access_token) setSession(data);
      return data;
    } catch (error) {
      const message = String(error && error.message ? error.message : error || '');
      if(message === 'Failed to fetch' || message.includes('fetch')){
        throw new Error('Backend server is unavailable. Start the API at http://127.0.0.1:8000 and try again.');
      }
      throw error;
    }
  }
  function htmlToPlainText(html=''){
    const d=document.createElement('div'); d.innerHTML=String(html||''); return d.innerText || d.textContent || '';
  }
  function jsonContent(data){
    try {
      const parsed = JSON.parse(data || '{}');
      const merged = {
        version: 3,
        type:'normal', color:'yellow', favorite:false, secret:false, pinned:false,
        text:'', items:[], rows:[], footer:'', tag:'', layout:'text', folderId:null,
        reminderAt:null, reminderLabel:'', images:[], audio:null, doodle:null,
        ...parsed
      };
      if(!merged.text && merged.html) merged.text=htmlToPlainText(merged.html);
      return merged;
    } catch {
      return {version:3,type:'normal',color:'yellow',favorite:false,secret:false,pinned:false,text:String(data||''),items:[],rows:[],footer:'',tag:'',layout:'text',folderId:null,reminderAt:null,reminderLabel:'',images:[],audio:null,doodle:null};
    }
  }
  function serialize(note){ return JSON.stringify(note); }
  function normalizeTag(raw){ return String(raw||'').trim().replace(/^#+/,'').replace(/\s+/g,'-').toLowerCase(); }
  function escapeHtml(str=''){ return String(str).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
  function smartFormat(text='', allowUrls=false){
    let safe = escapeHtml(text);
    safe = safe.replace(/^##\s(.+)$/gm, '<strong class="note-heading">$1</strong>');
    safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    safe = safe.replace(/==(.+?)==/g, '<mark>$1</mark>');
    if(allowUrls) safe = safe.replace(/(https?:\/\/[^\s<]+)/g, '<a class="smart-url" href="$1" data-url="$1">$1</a>');
    return safe.replace(/\n/g,'<br>');
  }
  function linkify(text=''){ return smartFormat(text,true); }
  function parseDate(iso){
    if(!iso) return null;
    const value=String(iso);
    const normalized=/[zZ]|[+-]\d{2}:?\d{2}$/.test(value)?value:`${value}Z`;
    const d=new Date(normalized);
    return Number.isNaN(d.getTime())?null:d;
  }
  function dateTimeLabel(iso){
    const d=parseDate(iso); if(!d) return '';
    return d.toLocaleString(undefined,{year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
  }
  function dateLabel(iso){
    const d=parseDate(iso); if(!d) return '';
    const now=new Date(); const diff=(now-d)/1000;
    if(diff < 60) return 'just now'; if(diff < 3600) return `${Math.floor(diff/60)}m ago`; if(diff < 86400) return `${Math.floor(diff/3600)}h ago`; if(diff<172800) return 'yesterday';
    return d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
  }
  function toast(msg, icon='check_circle'){
    let el=document.getElementById('globalToast');
    if(!el){el=document.createElement('div');el.id='globalToast';el.className='toast';document.body.appendChild(el)}
    el.innerHTML=`<span class="material-symbols-outlined">${escapeHtml(icon)}</span><span>${escapeHtml(msg)}</span>`;
    el.classList.add('show'); clearTimeout(el._t); el._t=setTimeout(()=>el.classList.remove('show'),2600);
  }
  function localFolders(){
    try { return JSON.parse(localStorage.getItem('stickies_local_folders') || '[]'); }
    catch { return []; }
  }
  function saveLocalFolders(list){
    localStorage.setItem('stickies_local_folders', JSON.stringify(list || []));
  }
  function addLocalFolder(name){
    const list=localFolders();
    const clean=String(name||'').trim();
    if(!clean) throw new Error('Folder name is required');
    if(list.some(f=>f.name.toLowerCase()===clean.toLowerCase())) throw new Error('Folder already exists');
    const f={id:Date.now(), name:clean, created_at:new Date().toISOString(), local:true};
    list.push(f); saveLocalFolders(list); return f;
  }
  async function getFolders(){
    try { return await api('/folders'); }
    catch (e) {
      if(/404|401|not found|missing bearer|unavailable/i.test(String(e.message||''))) return localFolders();
      throw e;
    }
  }
  async function createFolder(name){
    try { return await api('/folders',{method:'POST',body:JSON.stringify({name})}); }
    catch (e) {
      if(/404|401|not found|missing bearer|unavailable/i.test(String(e.message||''))) return addLocalFolder(name);
      throw e;
    }
  }
  function logout(){ clearSession(); go('../lock_screen/code.html'); }
  function noteDefaults(type='normal'){
    const map={
      normal:{type:'normal',color:'yellow'},
      favorite:{type:'favorite',color:'lavender',favorite:true},
      secret:{type:'secret',color:'rose',secret:true},
      checklist:{type:'checklist',color:'mint'}
    };
    return {version:3,...map[type]||map.normal,favorite:!!map[type]?.favorite,secret:!!map[type]?.secret,pinned:false,text:'',items:[],rows:[],footer:'',tag:'',layout:'text',folderId:null,reminderAt:null,reminderLabel:'',images:[],audio:null,doodle:null};
  }
  function openEditor(type){ go(`../note_editor/code.html?type=${encodeURIComponent(type)}`); }
  function setupAutoLock(){
    if(!token()) return;
    const mode=localStorage.getItem('stickies_auto_lock')||'immediately';
    let seconds = mode==='1m'?60:mode==='5m'?300:mode==='15m'?900:0;
    let timer=null;
    const refresh=()=>{
      if(timer) clearTimeout(timer);
      if(seconds>0) timer=setTimeout(()=>logout(), seconds*1000);
    };
    ['click','keydown','touchstart','mousemove','scroll'].forEach(evt=>window.addEventListener(evt,refresh,{passive:true}));
    const internalNavPending=()=>{
      const t=Number(sessionStorage.getItem('stickies_internal_nav')||0);
      return t && Date.now()-t < 3000;
    };
    const onVisibility=()=>{
      if(document.visibilityState==='hidden' && seconds===0 && !internalNavPending()) logout();
    };
    document.addEventListener('visibilitychange',onVisibility);
    // Mark common internal links so the immediate-on-exit mode does not fire during navigation.
    document.addEventListener('click',e=>{
      const a=e.target.closest('a[href]');
      if(!a || a.target==='_blank') return;
      const href=a.getAttribute('href')||'';
      if(href && !href.startsWith('#') && !href.startsWith('http')) sessionStorage.setItem('stickies_internal_nav',String(Date.now()));
    },true);
    refresh();
  }
  function requirePage(){ if(!loginRequired()) return; setupAutoLock(); applyTheme(); requestNotificationPermissionIfNeeded(false); }
  function applyTheme(){ document.documentElement.dataset.theme=localStorage.getItem('stickies_theme')||'light'; }
  function toggleTheme(){ const next=(localStorage.getItem('stickies_theme')||'light')==='dark'?'light':'dark'; localStorage.setItem('stickies_theme',next); applyTheme(); return next; }
  async function requestNotificationPermissionIfNeeded(promptUser=true){
    if(!('Notification' in window)) { if(promptUser) toast('Browser notifications are not supported','notifications_off'); return 'unsupported'; }
    if(Notification.permission==='granted') return 'granted';
    if(promptUser){ try{return await Notification.requestPermission();}catch{return 'denied';} }
    return Notification.permission;
  }
  function scheduleReminderWatcher(){
    if(!token()) return null;
    const check=async()=>{
      try{
        const notes=await api('/notes'); const now=Date.now();
        for(const n of notes){
          const m=jsonContent(n.content); if(!m.reminderAt) continue;
          const when=new Date(m.reminderAt).getTime();
          if(Number.isNaN(when) || when>now) continue;
          const key=`stickies_fired_${n.id}_${m.reminderAt}`;
          if(localStorage.getItem(key)==='1') continue;
          localStorage.setItem(key,'1');
          toast(`Reminder: ${n.title}`,'notifications_active');
          if('Notification' in window && Notification.permission==='granted') new Notification('Stickies Vault Reminder',{body:n.title});
        }
      }catch{}
    };
    check(); return setInterval(check,30000);
  }
  return {API_URL,TOKEN_KEY,USER_KEY,token,user,setSession,clearSession,go,loginRequired,requirePage,api,jsonContent,serialize,normalizeTag,escapeHtml,linkify,smartFormat,dateLabel,dateTimeLabel,toast,logout,noteDefaults,openEditor,setupAutoLock,applyTheme,toggleTheme,requestNotificationPermissionIfNeeded,scheduleReminderWatcher,localFolders,saveLocalFolders,addLocalFolder,getFolders,createFolder};
})();
