/* ViralForge Sound Radar: visualizes scheduled, source-attributed observations. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const root = $("soundResults");
  if (!root) return;
  const platformLabels = {all:"All platforms",tiktok:"TikTok",instagram:"Instagram",youtube:"YouTube",facebook:"Facebook",x:"X"};
  let snapshot = null;
  const date = input => {
    const d = new Date(input || "");
    return isNaN(d.getTime()) ? "Not yet" : d.toLocaleString(undefined, {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  };
  const safeLink = input => {
    try {const u = new URL(input);return u.protocol === "https:" ? u.href : "";}
    catch {return "";}
  };
  const fmt = n => n === null || n === undefined || !Number.isFinite(Number(n)) ? "Not reported" : new Intl.NumberFormat(undefined,{notation:"compact",maximumFractionDigits:1}).format(Number(n));
  function el(tag, cls, value) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function draw() {
    root.replaceChildren();
    if (!snapshot) return;
    const platform = $("soundPlatform").value, region = $("soundRegion").value.trim().toUpperCase(), search = $("soundSearch").value.trim().toLowerCase();
    const rows = (Array.isArray(snapshot.sounds) ? snapshot.sounds : []).filter(s =>
      (platform === "all" || s.platform === platform) &&
      (!region || !s.region || s.region === region || s.region === "GLOBAL") &&
      (!search || (s.title+" "+s.artist+" "+s.platform).toLowerCase().includes(search))
    );
    $("soundCount").textContent = rows.length + " displayed / " + (snapshot.sound_count || 0) + " observed";
    $("soundChecked").textContent = "Feed checked " + date(snapshot.checked_at) + " · Last successful sync " + date(snapshot.last_success_at);
    $("soundProvider").textContent = snapshot.source || "No approved source";
    const status = snapshot.status;
    $("soundStatus").textContent = status === "ok" ? "SOURCE CONNECTED" : status === "feed_error" ? "SOURCE ERROR / CACHED" : "AWAITING DATA SOURCE";
    $("soundStatus").dataset.state = status;
    if (!rows.length) {
      const empty = el("div","sound-empty");
      empty.append(el("strong","",snapshot.sounds?.length ? "No matching sounds" : "Sound Radar is ready for a verified feed"),
        el("p","",snapshot.sounds?.length ? "Try another platform, region, or search." :
          "The eight-hour update job is installed. Configure SOUND_FEED_URL in your GitHub Actions secrets to receive actual ranked music/sound observations. We do not display fabricated charts."));
      root.append(empty);
      return;
    }
    for (const sound of rows) {
      const card = el("article","sound-card");
      const head = el("div","sound-card-head");
      const platform = el("span","sound-pill",platformLabels[sound.platform] || sound.platform);
      const rank = el("span","sound-rank",sound.rank == null ? "OBSERVED SOUND" : "CHART #" + sound.rank);
      head.append(platform,rank);
      card.append(head,el("h3","",sound.title),el("p","sound-artist",sound.artist));
      const stats = el("div","sound-stats");
      for (const [name,value] of [["Uses / 24h",fmt(sound.uses_24h)],["Growth / 24h",sound.growth_24h_pct == null ? "Not reported" : sound.growth_24h_pct+"%"],["Total uses",fmt(sound.total_uses)]]) {
        const stat = el("div","sound-stat");
        stat.append(el("span","",name),el("strong","",value));
        stats.append(stat);
      }
      card.append(stats);
      card.append(el("p","sound-observed","Observed "+date(sound.observed_at)+" · "+(sound.region || "GLOBAL")));
      const actions = el("div","sound-actions");
      const source = safeLink(sound.source_url);
      if (source) {
        const a = el("a","button secondary","OPEN SOUND ↗");
        a.href = source;a.target="_blank";a.rel="noopener noreferrer";actions.append(a);
      }
      const preview = safeLink(sound.preview_url);
      if (preview) {
        const audio = el("audio","sound-preview");
        audio.controls=true;audio.preload="none";audio.src=preview;
        audio.setAttribute("aria-label","Licensed preview of "+sound.title);
        actions.append(audio);
      }
      card.append(actions);
      root.append(card);
    }
  }
  async function refresh(force=false) {
    $("soundStatus").textContent = "LOADING SNAPSHOT";
    try {
      const response = await fetch("data/trend_sounds.json"+(force?"?t="+Date.now():""),{cache:"no-store"});
      if (!response.ok) throw Error("Sound snapshot unavailable ("+response.status+").");
      const result = await response.json();
      if (!result || !Array.isArray(result.sounds)) throw Error("Sound snapshot has an unexpected format.");
      snapshot = result;draw();
    } catch(error) {
      $("soundStatus").textContent = "SNAPSHOT UNAVAILABLE";
      root.replaceChildren(el("p","sound-empty",error.message));
    }
  }
  ["soundPlatform","soundRegion","soundSearch"].forEach(id => $(id).addEventListener(id==="soundSearch" ? "input":"change",draw));
  $("soundRefresh").addEventListener("click",()=>refresh(true));
  refresh();
  setInterval(()=>{if(!document.hidden)refresh(true);},15*60*1000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh(true);});
})();
