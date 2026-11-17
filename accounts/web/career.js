/* Read-only presentation rules. Unlock authority stays with the account service. */
(function(root){
  'use strict';
  function view(account){
    const profiles=Array.isArray(account?.profiles)?account.profiles:[];
    const pairing=profiles.some(row=>row?.live===true)?'confirmed':profiles.length?'confirm_again':'unlinked';
    const rows=account?.custom_challenges;
    const row=Array.isArray(rows)?rows.find(item=>item?.challenge==='outlands_dusk_an94_headshots'):null;
    const valid=row?.weapon==='an94_mp'&&row?.camo==='outlands_dusk'&&row?.scope==='outlands_account'
      &&row?.revision===1&&row?.target===25&&Number.isSafeInteger(row?.progress)&&row.progress>=0&&row.progress<=25
      &&typeof row?.completed==='boolean'&&row.completed===(row.progress===25);
    // A completion counter alone never creates an equip action.
    return {pairing,available:Boolean(valid),progress:valid?row.progress:null,target:25,
      completed:Boolean(valid&&row.completed),equip:false};
  }
  root.OutlandsCareer=Object.freeze({view});
})(typeof module==='object'&&module.exports?module.exports:window);
