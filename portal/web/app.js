'use strict';
const $ = id => document.getElementById(id);
const pages = ['match', 'contracts', 'rivals', 'armory', 'career'];
let current = null;
let rivals = [];
let toastTimer;
let lastSuccessful = 0;
const text = (id, value) => { $(id).textContent = value; };
const number = value => Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString() : '—';
function toast(message) {
  text('toast', message); $('toast').classList.add('visible');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('visible'), 4000);
}
function navigate() {
  const target = pages.includes(location.hash.slice(1)) ? location.hash.slice(1) : 'match';
  for (const page of pages) $(page).hidden = page !== target;
  for (const link of document.querySelectorAll('nav a')) {
    if (link.hash === '#' + target) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  const names = {match:'LIVE MATCH', contracts:'CONTRACTS', rivals:'AI RIVALS', armory:'ARMORY', career:'CAREER'};
  text('breadcrumb', names[target]); document.title = 'Outlands / ' + names[target];
}
window.addEventListener('hashchange', navigate); navigate();
async function copy(value, source) {
  if (!value) return;
  try {
    if (!navigator.clipboard || !window.isSecureContext) throw new Error('Manual copy');
    await navigator.clipboard.writeText(value); toast('Copied. Paste into BO2.');
  } catch {
    // HTTP tailnet pages may not have clipboard permission. Select the visible
    // command so desktop and mobile browsers can copy it without hidden fields.
    const node = source.closest('.command-line').querySelector('code');
    const selection = window.getSelection(); const range = document.createRange();
    range.selectNodeContents(node); selection.removeAllRanges(); selection.addRange(range);
    toast('Command selected. Use Copy from your browser.');
  }
}
$('copy-join').addEventListener('click', event => copy(current?.join_command, event.currentTarget));
for (const button of document.querySelectorAll('.copy-command'))
  button.addEventListener('click', event => copy(button.dataset.command, event.currentTarget));
$('fullscreen').addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
    else toast('Use your browser menu to hide its controls.');
  } catch { toast('Use your browser’s full-screen option.'); }
});
document.addEventListener('fullscreenchange', () => {
  $('fullscreen').firstChild.textContent = document.fullscreenElement ? 'Exit full screen ' : 'Full screen ';
});
function node(tag, className, value) {
  const element = document.createElement(tag); if (className) element.className = className;
  if (value !== undefined) element.textContent = value; return element;
}
function contracts(match) {
  const container = $('contract-cards'); container.replaceChildren();
  const seconds = match?.contract_seconds;
  text('contract-time', match ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')} REMAINING` : 'WAITING FOR SIGNAL');
  for (const team of ['allies', 'axis']) {
    const contract = match?.contracts?.find(value => value.team === team);
    const card = node('article', 'panel contract');
    card.append(node('div', 'eyebrow amber', team.toUpperCase() + ' / TEAM ASSIGNMENT'));
    card.append(node('h3', '', contract && contract.kind !== 'none' ? contract.label : 'Standing by'));
    if (!contract || contract.kind === 'none') {
      card.append(node('p', '', match?.mode === 'dm' ? 'Team contracts are unavailable in Free-for-All.' : 'No fresh team contract is available.'));
    } else {
      const count = node('div', 'contract-count', number(contract.progress));
      count.append(node('small', '', ' / ' + number(contract.goal))); card.append(count);
      const track = node('div', 'progress-track');
      const progress = node('div', 'progress-fill');
      progress.style.width = Math.min(100, Math.max(0, contract.progress / contract.goal * 100)) + '%';
      track.append(progress); card.append(track);
      card.append(node('p', contract.complete ? 'complete' : '', contract.complete ? 'ASSIGNMENT COMPLETE' : 'Contribute together. Every team action counts.'));
    }
    container.append(card);
  }
}
function renderRivals() {
  const filter = $('role-filter').value;
  const container = $('rival-cards'); container.replaceChildren();
  const visible = rivals.filter(rival => filter === 'all' || rival.role === filter);
  if (!visible.length) container.append(node('div', 'empty', 'No career records available for this role yet. AI careers appear as the server records their matches.'));
  for (const rival of visible) {
    const card = node('article', 'rival'); const badge = node('div', 'badge');
    badge.append(node('span', '', number(rival.level))); card.append(badge);
    card.append(node('div', 'role', rival.role)); card.append(node('h3', '', rival.alias));
    card.append(node('p', 'small dim', 'PRESTIGE ' + number(rival.prestige) + ' · LEVEL ' + number(rival.level)));
    const stats = node('div', 'rival-stats'); stats.append(node('span', '', number(rival.kills) + ' ELIMINATIONS'));
    stats.append(node('span', '', number(rival.rounds) + ' ROUNDS')); card.append(stats); container.append(card);
  }
}
$('role-filter').addEventListener('change', renderRivals);
function disconnected(message) {
  $('led').classList.remove('live'); text('connection', 'SIGNAL LOST');
  text('updated', message); text('match-title', 'STAND BY.'); text('mode', 'Waiting for a fresh server signal');
  text('match-state', 'AWAITING TELEMETRY');
  for (const id of ['players','allies-score','axis-score']) text(id, '—');
  text('population', 'Live counts unavailable'); text('allies-count', 'Team score / players'); text('axis-count', 'Team score / players');
  contracts(null);
}
function render(data) {
  current = data;
  if (/^connect [a-zA-Z0-9.:-]{1,255}:[0-9]{1,5}$/.test(data.join_command || '')) {
    text('join-command', data.join_command); $('copy-join').disabled = false;
  }
  rivals = Array.isArray(data.rivals) ? data.rivals : []; renderRivals();
  const age = data.observed_at ? Date.now()/1000-data.observed_at : Infinity;
  const match = data.live && age >= -2 && age <= 20 ? data.match : null;
  if (!match) { disconnected('Server signal unavailable'); return; }
  $('led').classList.add('live'); text('connection','SERVER LIVE');
  text('updated', 'Updated ' + new Date(data.observed_at*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}));
  text('match-title', match.map_name.toUpperCase() + '.'); text('mode', match.mode_name);
  text('match-state', match.state.toUpperCase()); text('players', number(match.humans + match.bots));
  text('population', `${number(match.humans)} human · ${number(match.bots)} AI`);
  for (const team of match.teams) {
    text(team.id + '-score', number(team.score)); text(team.id + '-count', number(team.players) + ' players on team');
  }
  contracts(match);
}
let controller;
async function refresh() {
  if (document.hidden) return;
  controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch('/api/status', {cache:'no-store', signal:controller.signal});
    if (!response.ok) throw new Error('No snapshot');
    const data = await response.json();
    if (data.schema !== 1 || Date.now()/1000-data.generated_at > 20 || Date.now()/1000-data.generated_at < -2) throw new Error('Old snapshot');
    render(data); lastSuccessful = Date.now();
  } catch { disconnected('Connection interrupted · retrying'); }
  finally { clearTimeout(timeout); controller = null; }
}
document.addEventListener('visibilitychange', () => {
  if (document.hidden) controller?.abort(); else refresh();
});
setInterval(() => { if (lastSuccessful && Date.now()-lastSuccessful > 20000) disconnected('Connection interrupted · retrying'); refresh(); }, 5000);
contracts(null); renderRivals(); refresh();
