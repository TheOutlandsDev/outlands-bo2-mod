'use strict';
const $=id=>document.getElementById(id);
let me=null,busy=false,version=0,lastSuccess=0,refreshController=null;
const message=text=>{$('message').textContent=text;};
const node=(tag,className,text)=>{const value=document.createElement(tag);value.className=className;value.textContent=text;return value;};
class AccountError extends Error{constructor(text,status){super(text);this.status=status;}}
async function request(path,body,signal){
  const options={cache:'no-store',credentials:'same-origin',signal:signal||AbortSignal.timeout(5000)};
  if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-Outlands-Request':'1'};options.body=JSON.stringify(body);}
  const response=await fetch(path,options);let value;
  try{value=await response.json();}catch(error){throw new AccountError('Account service unavailable',response.status);}
  if(!response.ok)throw new AccountError(value.error||'Account request unavailable',response.status);
  return value;
}
function invalidate(){version++;if(refreshController)refreshController.abort();}
function career(account,stale=false){
  const view=OutlandsCareer.view(account);
  const pairing={confirmed:['PROFILE CONFIRMED','A linked profile has a fresh server observation.'],
    confirm_again:['CONFIRM YOUR SESSION','Your saved link remains. Join and confirm the current game session to resume earning.'],
    unlinked:['LINK YOUR GAME PROFILE','Join Outlands and request a private pairing code to connect your career.']};
  const [title,detail]=pairing[view.pairing];
  $('pairing-state').textContent=stale?'CONNECTION INTERRUPTED':title;
  $('pairing-detail').textContent=stale?'Current pairing status could not be checked. Your saved links have not been removed.':detail;
  $('pairing-state').className='pairing-state'+(!stale&&view.pairing==='confirmed'?' confirmed':'');
  const available=!stale&&view.available;
  $('challenge-state').textContent=stale?'PROGRESS UNAVAILABLE':!available?'PREVIEW UNAVAILABLE':view.completed?'CHALLENGE COMPLETE':'CHALLENGE IN PROGRESS';
  $('challenge-state').className='tag'+(available&&view.completed?' complete':'');
  $('challenge-count').textContent=available?String(view.progress):'—';
  $('challenge-progress').hidden=!available;
  $('challenge-progress').value=available?view.progress:0;
  $('challenge-detail').textContent=stale?'Your last update could not be refreshed. We will reconnect automatically.':
    !available?'Challenge progress is not available from this server yet. An unavailable counter does not mean your progress is zero.':
    view.completed?'All 25 qualifying headshots are recorded on your Outlands account. Camo equipping is not available yet.':
    'Earn confirmed enemy headshots with the AN-94 while your current game session is linked. Delivery can take a moment.';
  $('equip-camo').disabled=true;
  $('career-updated').textContent=lastSuccess&&!stale?'UPDATED '+new Date(lastSuccess).toLocaleTimeString():'WAITING FOR ACCOUNT DATA';
}
function clearPrivate(){
  me=null;lastSuccess=0;$('guest').hidden=false;$('member').hidden=true;
  $('profiles').replaceChildren();$('display-name').value='';$('pair-code').value='';career(null);
}
function profiles(rows){
  $('profiles').replaceChildren();
  if(!rows.length){$('profiles').append(node('p','empty','No profiles linked yet. Use a private pairing code from your current game session.'));return;}
  for(const row of rows){
    const panel=node('article','panel','');panel.append(node('div','eyebrow amber',row.server));
    panel.append(node('h2','',row.live?'LIVE PROFILE':'LAST OBSERVED PROFILE'));
    const seen=row.observed_at?new Date(row.observed_at*1000).toLocaleString():'No stat snapshot yet';panel.append(node('p','small dim',seen));
    if(row.stats){for(const [key,value] of Object.entries(row.stats)){const line=node('div','quick-command','');line.append(node('span','',key.replaceAll('_',' ').toUpperCase()),node('strong','',Number(value).toLocaleString()));panel.append(line);}}
    else panel.append(node('p','dim','Stats unavailable. Join and confirm your current game profile.'));
    $('profiles').append(panel);
  }
}
async function refresh(){
  if(document.hidden||busy)return;
  invalidate();const current=version;const controller=new AbortController();refreshController=controller;
  const timer=setTimeout(()=>controller.abort(),5000);
  try{
    const value=await request('/api/me',undefined,controller.signal);
    if(current!==version)return;
    if(!value||typeof value.id!=='string'||typeof value.display_name!=='string'||!Array.isArray(value.profiles))throw new Error('Invalid account view');
    const accountChanged=me!==null&&me.id!==value.id;
    if(accountChanged)clearPrivate();
    me=value;lastSuccess=Date.now();$('guest').hidden=true;$('member').hidden=false;
    if(accountChanged||document.activeElement!==$('display-name'))$('display-name').value=me.display_name;
    profiles(me.profiles);career(me);message('Signed in. Outlands challenges follow your account; native BO2 saves remain on their PCs.');
  }catch(error){
    if(current!==version)return;
    if(error.status===401){clearPrivate();message('Sign in to view your linked profiles and career.');}
    else{career(me,true);message('Connection interrupted. Current career data is unavailable.');for(const label of document.querySelectorAll('#profiles h2'))label.textContent='CONNECTION INTERRUPTED';}
  }finally{clearTimeout(timer);if(current===version)refreshController=null;}
}
async function submit(event,path,body){
  event.preventDefault();if(busy)return;busy=true;invalidate();const buttons=[...event.target.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  let saved=false;
  try{await request(path,body);if(path==='/api/link')$('pair-code').value='';message('Saved.');saved=true;}
  catch(error){message(error.message);}
  finally{busy=false;buttons.forEach(b=>b.disabled=false);}
  if(saved)await refresh();
}
$('profile-form').addEventListener('submit',event=>{if(me)submit(event,'/api/profile',{display_name:$('display-name').value,revision:me.revision});});
$('link-form').addEventListener('submit',event=>submit(event,'/api/link',{code:$('pair-code').value.trim().toUpperCase()}));
$('logout').addEventListener('click',async()=>{
  if(busy)return;busy=true;invalidate();$('logout').disabled=true;
  try{await request('/api/logout',{});clearPrivate();message('Signed out. Your private career data has been cleared from this page.');}
  catch(error){career(me,true);message('Sign-out could not be confirmed. Please try again.');}
  finally{busy=false;$('logout').disabled=false;}
});
career(null);refresh();setInterval(refresh,10000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){if(lastSuccess&&Date.now()-lastSuccess>30000)career(me,true);refresh();}});
