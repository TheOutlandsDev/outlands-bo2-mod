'use strict';
const $=id=>document.getElementById(id);
let me=null;
let busy=false;
const message=text=>{$('message').textContent=text;};
const node=(tag,className,text)=>{const value=document.createElement(tag);value.className=className;value.textContent=text;return value;};
async function request(path,body){
  const options={cache:'no-store',credentials:'same-origin',signal:AbortSignal.timeout(5000)};
  if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json','X-Outlands-Request':'1'};options.body=JSON.stringify(body);}
  const response=await fetch(path,options);const value=await response.json();
  if(!response.ok)throw new Error(value.error||'Account request unavailable');return value;
}
function profiles(rows){
  $('profiles').replaceChildren();
  if(!rows.length){$('profiles').append(node('p','empty','No profiles linked yet. Your host must enable native pairing before live stats can appear here.'));return;}
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
  try{me=await request('/api/me');$('guest').hidden=true;$('member').hidden=false;
    if(document.activeElement!==$('display-name'))$('display-name').value=me.display_name;
    profiles(me.profiles);message('Signed in. Your native saves remain on their PCs.');
  }catch(error){
    if(error.message==='Sign-in required'){$('guest').hidden=false;$('member').hidden=true;me=null;message('Sign in to view your linked profiles.');}
    else{message('Connection interrupted. Profile data may be out of date.');for(const label of document.querySelectorAll('#profiles h2'))label.textContent='CONNECTION INTERRUPTED';}
  }
}
async function submit(event,path,body){event.preventDefault();if(busy)return;busy=true;const buttons=[...event.target.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try{await request(path,body);if(path==='/api/link')$('pair-code').value='';message('Saved.');}
  catch(error){message(error.message);return;}
  finally{busy=false;buttons.forEach(b=>b.disabled=false);}
  await refresh();
}
$('profile-form').addEventListener('submit',event=>{if(me)submit(event,'/api/profile',{display_name:$('display-name').value,revision:me.revision});});
$('link-form').addEventListener('submit',event=>submit(event,'/api/link',{code:$('pair-code').value.trim().toUpperCase()}));
$('logout').addEventListener('click',async()=>{try{await request('/api/logout',{});await refresh();}catch(error){message(error.message);}});
refresh();setInterval(refresh,10000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
