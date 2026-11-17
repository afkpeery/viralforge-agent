/* ViralForge Video Lab. Browser-only processing: selected files never leave the device. */
(function () {
  "use strict";
  const get = (id) => document.getElementById(id);
  const fileInput = get("videoFile");
  if (!fileInput) return;
  const video = get("videoPreview");
  const textPanel = get("videoDropText");
  const status = get("videoFileStatus");
  const run = get("videoAnalyzeBtn");
  const platformSelect = get("videoPlatform");
  const progressText = get("videoLabProgress");
  const progressFill = get("videoMeterFill");
  const results = get("videoLabLive");
  const evidenceEl = get("videoLabMetrics");
  const chart = get("videoLabTimeline");
  const recommendationsEl = get("videoLabRecommendations");
  const audioOpt = get("videoAnalyzeAudio");
  let previewUrl = null, lastReport = null, busy = false;

  function htmlEscape(v) {
    return String(v === null || v === undefined ? "" : v).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }
  function setProgress(message, value) {
    progressText.textContent = message;
    progressFill.style.width = Math.max(0, Math.min(100, value)) + "%";
  }
  function platform() {
    const raw = get("postUrl") && get("postUrl").value.trim();
    if (raw && typeof postIdentity === "function") {
      try { return postIdentity(raw).platform; } catch (_) { /* standalone file is still valid */ }
    }
    return platformSelect.value;
  }
  function formatTime(t) {
    if (!isFinite(t)) return "—";
    const n = Math.max(0, Math.round(t));
    return Math.floor(n / 60) + ":" + String(n % 60).padStart(2, "0");
  }
  function cleanupUrl() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  function listenUntil(element, goodEvent, badEvent, limitMs) {
    return new Promise(function (resolve, reject) {
      let timer;
      function clean() {
        clearTimeout(timer);
        element.removeEventListener(goodEvent, ok);
        element.removeEventListener(badEvent, bad);
      }
      function ok() { clean(); resolve(); }
      function bad() { clean(); reject(new Error("This file could not be decoded by your browser. Try MP4 (H.264) or WebM.")); }
      element.addEventListener(goodEvent, ok, {once:true});
      element.addEventListener(badEvent, bad, {once:true});
      timer = setTimeout(function () { clean(); reject(new Error("Media loading timed out. Try a smaller MP4 or WebM file.")); }, limitMs);
    });
  }
  async function loadSelectedFile() {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    lastReport = null;
    results.hidden = true;
    setProgress("File selected. Ready to inspect frames.", 0);
    if (file.size > 250 * 1024 * 1024) {
      status.textContent = "File exceeds the 250 MB local-analysis limit.";
      fileInput.value = "";
      return;
    }
    if (!/^video\//.test(file.type) && !/\.(mp4|webm|mov|m4v|ogv)$/i.test(file.name)) {
      status.textContent = "Choose a video file (MP4, WebM, MOV or M4V).";
      fileInput.value = "";
      return;
    }
    if (busy) return;
    video.pause();
    cleanupUrl();
    previewUrl = URL.createObjectURL(file);
    const loaded = listenUntil(video, "loadedmetadata", "error", 16000);
    video.src = previewUrl;
    video.load();
    status.textContent = file.name + " · " + (file.size / (1024*1024)).toFixed(1) + " MB";
    try {
      await loaded;
      if (!isFinite(video.duration) || video.duration <= 0 || video.videoWidth < 2) {
        throw new Error("This video does not expose usable duration or frames in your browser.");
      }
      textPanel.hidden = true;
      video.hidden = false;
      status.textContent += " · " + formatTime(video.duration) + " · " + video.videoWidth + "×" + video.videoHeight;
      setProgress("Ready to sample visual frames and optional audio. Nothing is uploaded.", 0);
    } catch (error) {
      video.hidden = true;
      textPanel.hidden = false;
      status.textContent = error.message;
      cleanupUrl();
    }
  }
  async function seek(t) {
    if (Math.abs(video.currentTime - t) < .025 && video.readyState >= 2) return;
    const wait = listenUntil(video, "seeked", "error", 12000);
    video.currentTime = t;
    await wait;
  }
  function samplePixels(ctx, width, height) {
    ctx.drawImage(video, 0, 0, width, height);
    const pixels = ctx.getImageData(0, 0, width, height).data;
    let lumSum = 0, lumSq = 0;
    const luma = new Float32Array(width * height);
    for (let p = 0, k = 0; p < pixels.length; p += 4, k++) {
      const value = (.2126*pixels[p] + .7152*pixels[p+1] + .0722*pixels[p+2]) / 255;
      luma[k] = value; lumSum += value; lumSq += value * value;
    }
    const brightness = lumSum / luma.length;
    return {luma, brightness, contrast: Math.sqrt(Math.max(0, lumSq/luma.length - brightness*brightness))};
  }
  async function visualSignals(duration) {
    const canvas = document.createElement("canvas");
    canvas.width = 96; canvas.height = 54;
    const ctx = canvas.getContext("2d", {willReadFrequently: true});
    if (!ctx) throw new Error("Canvas inspection is unavailable in this browser.");
    const count = Math.min(24, Math.max(4, Math.ceil(duration / 1.3)));
    const end = Math.max(.08, duration - .12);
    const frames = [], changes = [];
    let previous = null, firstChange = null, largeChanges = 0, sumChanges = 0, sumLight = 0;
    for (let i = 0; i < count; i++) {
      const t = Math.min(end, Math.max(.02, (.15 + (i / (count - 1)) * (duration - .35))));
      await seek(t);
      const frame = samplePixels(ctx, canvas.width, canvas.height);
      frames.push({t, brightness: frame.brightness, contrast: frame.contrast, thumbnail: canvas.toDataURL("image/jpeg", .65)});
      sumLight += frame.brightness;
      if (previous) {
        let delta = 0;
        for (let k = 0; k < frame.luma.length; k++) delta += Math.abs(frame.luma[k] - previous[k]);
        delta /= frame.luma.length;
        changes.push({t, delta});
        sumChanges += delta;
        if (delta > .18) { largeChanges++; if (firstChange === null) firstChange = t; }
      }
      previous = frame.luma;
      setProgress("Sampling frame " + (i+1) + " of " + count, 8 + (i+1)/count*67);
    }
    const introFrames = frames.filter(function (f) { return f.t <= 3.1; });
    return {
      frames, changes, frame_samples: frames.length,
      sample_interval_seconds: duration/Math.max(1, count-1),
      mean_brightness: sumLight/frames.length,
      opening_contrast: (introFrames.length ? introFrames : frames.slice(0,1)).reduce(function (s, f) { return s+f.contrast; },0)/Math.max(1,introFrames.length),
      mean_frame_change: sumChanges/Math.max(1,changes.length),
      sampled_change_events: largeChanges,
      first_change_at_seconds: firstChange
    };
  }
  async function audioSignals(file, duration) {
    if (!audioOpt.checked) return {note:"Audio check was turned off.",quiet_segment_fraction:null,near_peak_fraction:null};
    if (file.size > 28 * 1024 * 1024 || duration > 240) {
      return {note:"Audio decoding skipped for larger/longer files (28 MB / 4 min local limit).",quiet_segment_fraction:null,near_peak_fraction:null};
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return {note:"Web Audio decoding is not available in this browser.",quiet_segment_fraction:null,near_peak_fraction:null};
    let context;
    try {
      context = new Ctx();
      const buffer = await context.decodeAudioData(await file.arrayBuffer());
      const channel = buffer.getChannelData(0), step = Math.max(1,Math.round(buffer.sampleRate*.5));
      const jump = Math.max(1, Math.floor(buffer.sampleRate/9000));
      let quiet = 0, windows = 0, nearPeak = 0, total = 0;
      for (let i = 0; i < channel.length; i += step) {
        let energy = 0, n = 0;
        for (let j = i; j < Math.min(channel.length, i+step); j += jump) {
          const v = channel[j]; energy += v*v; n++;
          if (Math.abs(v) >= .985) nearPeak++;
          total++;
        }
        if (Math.sqrt(energy/Math.max(1,n)) < .018) quiet++;
        windows++;
      }
      return {note:"Decoded audio energy (not speech transcription).",quiet_segment_fraction:quiet/Math.max(1,windows),near_peak_fraction:nearPeak/Math.max(1,total)};
    } catch (_) {
      return {note:"Audio decode was unavailable for this codec; visual analysis is still valid.",quiet_segment_fraction:null,near_peak_fraction:null};
    } finally { if (context) await context.close().catch(function () {}); }
  }
  function guidance(report) {
    const s = report.signals, tips = [];
    function add(title, note, action, measure) { tips.push({title,note,action,measure}); }
    if (s.opening_contrast < .13) add("OPENING FRAME","Measured low opening image contrast.","Check that the subject and any on-screen text stand out on a phone. Test a cleaner or brighter first shot.","First 3-second retention");
    else add("HOOK TEST","The sampled opening has visible image contrast; its meaning is unknown.","Create two alternate openings: start with the payoff versus a short direct question.","First 3-second retention");
    if (s.mean_brightness < .26) add("MOBILE VISIBILITY","Sampled frames have relatively low average brightness.","Review on a dim phone screen. Brighten important details or increase caption contrast, if necessary.","Retention and qualitative feedback");
    if (s.sampled_change_events >= Math.max(3,Math.round(s.frame_samples*.55))) add("VISUAL PACING","Large changes appear frequently between sampled frames.","Consider letting the most important proof or reveal breathe before the next cut.","Completion and average view duration");
    else if (s.mean_frame_change < .11 && report.duration_seconds >= 8) add("VISUAL VARIETY","Sampled frames differ relatively little.","Try a relevant insert, camera angle or graphic at a flat moment, without adding distracting cuts.","Retention curve");
    if (s.first_change_at_seconds !== null && s.first_change_at_seconds > 3) add("FIRST 3 SECONDS","The first substantial sampled visual change came after 3 seconds.","Test moving a compelling visual reveal or clear demonstration earlier.","3- and 5-second retention");
    if (s.quiet_segment_fraction !== null && s.quiet_segment_fraction > .30) add("AUDIO RHYTHM","Many decoded audio windows had low energy.","Listen for accidental pauses or hard-to-hear dialogue; trim or rebalance only where warranted.","Retention around quiet passages");
    if (s.near_peak_fraction !== null && s.near_peak_fraction > .02) add("AUDIO HEADROOM","A high proportion of samples approach full digital amplitude.","Listen for clipping; test lower gain or limiting if the mix distorts.","Headphone review");
    const rules = (typeof COACH_RULES !== "undefined" && COACH_RULES[report.platform]) || [];
    rules.slice(0,2).forEach(function (r) { add(r[0].toUpperCase(),"Platform-specific experiment; not measured by video pixels.",r[1],r[2]); });
    if (report.goal === "leads" || report.goal === "sales") add("CONVERSION HANDOFF","A conversion objective was selected.","Show a concrete benefit before one trackable CTA that matches the clip.","Qualified conversions per 1,000 views");
    return tips;
  }
  function render(report) {
    const s=report.signals;
    results.hidden=false;
    const metrics=[
      ["Video duration",formatTime(report.duration_seconds)],
      ["Frames sampled",String(s.frame_samples)],
      ["Mean brightness",Math.round(s.mean_brightness*100)+"%"],
      ["Opening contrast",Math.round(s.opening_contrast*100)+"%"],
      ["Sampled frame changes",String(s.sampled_change_events)],
      ["Audio energy windows",s.quiet_segment_fraction===null?"Unavailable":Math.round(s.quiet_segment_fraction*100)+"% quiet"]
    ];
    evidenceEl.innerHTML=metrics.map(function (m) { return "<span><strong>"+htmlEscape(m[0])+":</strong> "+htmlEscape(m[1])+"</span>"; }).join("");
    const changes=s.changes;
    chart.innerHTML=changes.map(function (p) {
      return '<i title="'+htmlEscape(p.t.toFixed(1))+'s · '+htmlEscape(Math.round(p.delta*100))+'% sampled frame change" style="height:'+Math.max(7,Math.min(95,p.delta*210+6))+'%"></i>';
    }).join("");
    chart.setAttribute("aria-label","Sampled-frame visual change chart. Greater bars mean larger pixel differences between sampled frames.");
    const storyboard = get("videoLabStoryboard");
    const chosen = s.frames.filter(function (_, i) { return i % Math.max(1, Math.ceil(s.frames.length / 8)) === 0; }).slice(0,8);
    storyboard.innerHTML=chosen.map(function (frame) {
      return '<figure class="lab-frame"><img src="'+frame.thumbnail+'" alt="Locally sampled video frame at '+htmlEscape(frame.t.toFixed(1))+' seconds"><figcaption>'+htmlEscape(formatTime(frame.t))+' / '+htmlEscape(frame.t.toFixed(1))+'s</figcaption></figure>';
    }).join("");
    const items=guidance(report);
    recommendationsEl.innerHTML=items.map(function (x,i) {
      return '<article class="lab-recommendation"><div class="lab-index">EXPERIMENT '+String(i+1).padStart(2,"0")+'</div><b>'+htmlEscape(x.title)+'</b><p>'+htmlEscape(x.note)+'</p><p>'+htmlEscape(x.action)+'</p><small>Evaluate: '+htmlEscape(x.measure)+'</small></article>';
    }).join("");
    get("videoLabEvidenceNote").textContent="LOCAL EVIDENCE · "+s.frame_samples+" decoded frame samples · "+report.audio_note+" These are creative hypotheses. Pixel changes are not exact cut detection; audio energy is not speech recognition. No private platform statistics or viral probability were measured.";
    get("videoLabLiveTitle").textContent="Your "+({"tiktok":"TikTok","instagram":"Instagram","x":"X","facebook":"Facebook","youtube":"YouTube"}[report.platform])+" edit plan";
    setProgress("Analysis complete · "+items.length+" editing experiments ready.",100);
  }
  async function analyze() {
    if (busy) return;
    const file=fileInput.files && fileInput.files[0];
    if (!file || video.hidden) { setProgress("Choose a supported local video first.",0); return; }
    if (!video.duration || !isFinite(video.duration)) { setProgress("Video duration is unavailable.",0);return; }
    busy=true;run.disabled=true;run.textContent="INSPECTING FRAMES…";results.hidden=true;video.pause();video.controls=false;
    try {
      const duration=video.duration;
      const signals=await visualSignals(duration);
      setProgress("Inspecting optional local audio…",80);
      const audio=await audioSignals(file,duration);
      signals.quiet_segment_fraction=audio.quiet_segment_fraction;
      signals.near_peak_fraction=audio.near_peak_fraction;
      const report={platform:platform(),goal:get("videoGoal").value,duration_seconds:duration,signals,audio_note:audio.note};
      lastReport=report;
      render(report);
      video.currentTime=0;
    } catch (error) {
      setProgress("Analysis stopped: "+error.message,0);
    } finally {
      busy=false;run.disabled=false;run.textContent="INSPECT MY VIDEO ↗";video.controls=true;
    }
  }
  get("videoFile").addEventListener("change",loadSelectedFile);
  run.addEventListener("click",analyze);
  const copy=get("videoCopyReport");
  copy.addEventListener("click",async function () {
    if (!lastReport) { setProgress("Analyze a video first.",0);return; }
    const exportData={platform:lastReport.platform,goal:lastReport.goal,duration_seconds:lastReport.duration_seconds,
      metrics:{...lastReport.signals,frames:undefined,changes:undefined},recommendations:guidance(lastReport),
      source:"local_creator_selected_file",notice:"No video file or transcript included."};
    const data=JSON.stringify(exportData,null,2);
    try {await navigator.clipboard.writeText(data);copy.textContent="REPORT COPIED ✓";}
    catch (_) {
      const blob=new Blob([data],{type:"application/json"});
      const href=URL.createObjectURL(blob),a=document.createElement("a");
      a.href=href;a.download="viralforge-video-insights.json";a.click();
      setTimeout(function(){URL.revokeObjectURL(href);},1000);
      copy.textContent="REPORT EXPORTED ✓";
    }
    setTimeout(function () {copy.textContent="COPY / EXPORT REPORT";},1800);
  });
  window.addEventListener("beforeunload",cleanupUrl);
})();
