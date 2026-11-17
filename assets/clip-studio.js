/* ViralForge Clip Studio — local files only, no uploads, streaming browser exports. */
(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  if (!$("clipFile")) return;
  const input = $("clipFile"), player = $("clipPreview");
  let fileURL = "", duration = 0, clips = [], nextId = 1, exporting = false, previewEnd = null;
  const MAX_BYTES = 250 * 1024 * 1024, MAX_CLIPS = 24, MAX_EXPORT_DURATION = 120;
  const stamp = n => {
    const s = Math.max(0, Math.floor(n));
    return Math.floor(s/60)+":"+String(s%60).padStart(2,"0");
  };
  const round = n => Math.round(n*100)/100;
  const status = msg => $("clipStatus").textContent=msg;
  const filename = s => (s || "clip").replace(/[^a-z0-9_-]+/gi,"-").replace(/^-+|-+$/g,"").slice(0,60) || "clip";
  const waitEvent = (node, event, fail="error", ms=15000) => new Promise((resolve,reject)=>{
    let timer;
    function done(){clearTimeout(timer);node.removeEventListener(event,ok);node.removeEventListener(fail,bad);}
    function ok(){done();resolve();}
    function bad(){done();reject(Error("The selected video could not be decoded."));}
    node.addEventListener(event,ok,{once:true});node.addEventListener(fail,bad,{once:true});
    timer=setTimeout(()=>{done();reject(Error("Media loading took too long."));},ms);
  });
  const download = (blob,name) => {
    const url=URL.createObjectURL(blob), a=document.createElement("a");
    a.href=url;a.download=name;document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),30000);
  };
  const checkFile = file => {
    if (!file) throw Error("Select a local video to begin.");
    if (file.size>MAX_BYTES) throw Error("Choose a file no larger than 250 MB.");
    if (!/^video\//.test(file.type) && !/\.(mp4|mov|m4v|webm|ogv)$/i.test(file.name)) throw Error("Choose MP4, MOV, WebM or OGV video.");
  };
  const validateRange = (start,end) => {
    if (!duration) throw Error("Load a video first.");
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > duration + .01 || end-start < .25)
      throw Error("Choose valid in/out points at least 0.25 seconds apart.");
    return {start:round(start),end:round(Math.min(duration,end))};
  };
  function render() {
    const list=$("clipList");list.replaceChildren();
    $("clipCount").textContent=clips.length+" clips";
    $("clipExportAll").disabled=exporting || !clips.length;
    $("clipAdd").disabled=exporting || !duration;
    $("clipSplit").disabled=exporting || !duration;
    const track=$("clipTimeline");track.replaceChildren();
    for (const c of clips) {
      const strip=document.createElement("button");
      strip.type="button";strip.className="clip-strip";strip.title=c.name+" / "+stamp(c.start)+" – "+stamp(c.end);
      strip.style.left=(c.start/duration*100)+"%";strip.style.width=Math.max(.5,(c.end-c.start)/duration*100)+"%";
      strip.addEventListener("click",()=>preview(c));strip.disabled=exporting;
      track.append(strip);
      const card=document.createElement("article");card.className="clip-entry";
      const top=document.createElement("div");top.className="clip-entry-main";
      const name=document.createElement("input");name.type="text";name.value=c.name;name.maxLength=60;
      name.setAttribute("aria-label","Clip filename");name.disabled=exporting;
      name.addEventListener("change",()=>{c.name=filename(name.value);name.value=c.name;});
      const time=document.createElement("span");time.textContent=stamp(c.start)+" – "+stamp(c.end)+" · "+round(c.end-c.start)+"s";
      top.append(name,time);
      const actions=document.createElement("div");actions.className="clip-entry-actions";
      for (const [label,action] of [["PREVIEW",()=>preview(c)],["DOWNLOAD",()=>exportOne(c)],["REMOVE",()=>{clips=clips.filter(x=>x.id!==c.id);render();}]]) {
        const btn=document.createElement("button");
        btn.type="button";btn.className=label==="DOWNLOAD"?"button":"button secondary";
        btn.textContent=label;btn.disabled=exporting;btn.addEventListener("click",action);actions.append(btn);
      }
      card.append(top,actions);list.append(card);
    }
    if (!clips.length) list.append(Object.assign(document.createElement("p"),{className:"clip-empty",textContent:"No clips yet. Add an in/out selection or split the video automatically."}));
  }
  function preview(c) {
    previewEnd=c.end;
    player.pause();
    player.currentTime=c.start;
    player.play().catch(()=>status("Press play on the preview to watch this segment."));
    status("Previewing "+c.name+" · "+stamp(c.start)+" – "+stamp(c.end));
  }
  player.addEventListener("timeupdate",()=>{if(previewEnd!==null && player.currentTime>=previewEnd-.04){player.pause();previewEnd=null;}});
  async function load(file) {
    if (exporting) return;
    try {
      checkFile(file);player.pause();previewEnd=null;
      if(fileURL)URL.revokeObjectURL(fileURL);
      fileURL=URL.createObjectURL(file);
      const loaded=waitEvent(player,"loadedmetadata");
      player.src=fileURL;player.load();await loaded;
      if (!Number.isFinite(player.duration) || player.duration <= .25 || !player.videoWidth) throw Error("Cannot read this video's timeline in your browser.");
      duration=player.duration;clips=[];nextId=1;
      $("clipStart").value=0;$("clipEnd").value=round(duration);
      $("clipSourceLabel").textContent=file.name+" · "+stamp(duration)+" · "+player.videoWidth+"×"+player.videoHeight;
      $("clipPreview").hidden=false;$("clipPlaceholder").hidden=true;
      status("Ready to cut. Export works locally at video playback speed; keep this tab open.");
      render();
    } catch(error) {
      duration=0;clips=[];player.removeAttribute("src");player.load();
      $("clipPreview").hidden=true;$("clipPlaceholder").hidden=false;
      status(error.message);render();
    }
  }
  input.addEventListener("change",()=>load(input.files?.[0]));
  const drop=$("clipDrop");
  drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("dragging");});
  drop.addEventListener("dragleave",()=>drop.classList.remove("dragging"));
  drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("dragging");load(e.dataTransfer.files?.[0]);});
  $("clipAdd").addEventListener("click",()=>{
    try {
      if(clips.length>=MAX_CLIPS)throw Error("Maximum "+MAX_CLIPS+" clips per project.");
      const range=validateRange(Number($("clipStart").value),Number($("clipEnd").value));
      clips.push({...range,id:nextId,name:"clip-"+String(nextId).padStart(2,"0")});
      nextId++;render();status("Clip added. Download it or export the collection as ZIP.");
    }catch(e){status(e.message);}
  });
  $("clipSplit").addEventListener("click",()=>{
    try {
      if(!duration)throw Error("Choose a video first.");
      const size=Number($("clipLength").value);
      if(!Number.isFinite(size)||size<1||size>120)throw Error("Split length must be between 1 and 120 seconds.");
      const count=Math.ceil(duration/size);
      if(count>MAX_CLIPS)throw Error("That would create "+count+" clips. Raise split length or choose a shorter video (maximum "+MAX_CLIPS+").");
      clips=[];nextId=1;
      for(let start=0;start<duration-.24;start+=size) {
        const end=Math.min(duration,start+size);
        clips.push({id:nextId,name:"clip-"+String(nextId).padStart(2,"0"),start:round(start),end:round(end)});
        nextId++;
      }
      render();status("Split into "+clips.length+" segments. Preview or download each one.");
    }catch(e){status(e.message);}
  });
  $("clipUsePlayheadStart").addEventListener("click",()=>{$("clipStart").value=round(player.currentTime||0);});
  $("clipUsePlayheadEnd").addEventListener("click",()=>{$("clipEnd").value=round(player.currentTime||0);});
  function preferredMime() {
    if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) throw Error("This browser cannot export video with MediaRecorder and canvas capture. Try current Chrome, Firefox, or Safari.");
    const choices=["video/mp4;codecs=avc1.42E01E,mp4a.40.2","video/webm;codecs=vp9,opus","video/webm;codecs=vp8,opus","video/webm","video/mp4"];
    const mime=choices.find(s=>MediaRecorder.isTypeSupported(s));
    if(!mime)throw Error("No supported browser video export format was found.");
    return mime;
  }
  async function encodeClip(c,part,total) {
    const mime=preferredMime(), extension=mime.includes("mp4")?"mp4":"webm";
    if(c.end-c.start>MAX_EXPORT_DURATION+.01) throw Error("Clip '"+c.name+"' exceeds the "+MAX_EXPORT_DURATION+"-second export limit. Split it into smaller segments.");
    const video=document.createElement("video");
    video.playsInline=true;video.preload="auto";
    video.style.cssText="position:fixed;left:-10000px;top:0;width:2px;height:2px;pointer-events:none";
    document.body.append(video);
    let tick=null, ctx=null, videoStream=null, outputStream=null, recorder=null, audioContext=null;
    try {
      const ready=waitEvent(video,"loadedmetadata");
      video.src=fileURL;video.load();await ready;
      if(c.start>.02){
        const seeked=waitEvent(video,"seeked");
        video.currentTime=c.start;await seeked;
      }
      const cap=Math.min(1,Math.sqrt(2073600/(video.videoWidth*video.videoHeight)));
      const canvas=document.createElement("canvas");
      canvas.width=Math.max(2,Math.round(video.videoWidth*cap/2)*2);
      canvas.height=Math.max(2,Math.round(video.videoHeight*cap/2)*2);
      const draw=canvas.getContext("2d",{alpha:false});
      if(!draw)throw Error("Canvas video encoding is unavailable.");
      draw.drawImage(video,0,0,canvas.width,canvas.height);
      videoStream=canvas.captureStream(30);
      const tracks=[...videoStream.getVideoTracks()];
      const AudioClass=window.AudioContext||window.webkitAudioContext;
      if(AudioClass) {
        audioContext=new AudioClass();
        const audioSource=audioContext.createMediaElementSource(video);
        const audioOut=audioContext.createMediaStreamDestination();
        audioSource.connect(audioOut);
        tracks.push(...audioOut.stream.getAudioTracks());
        await audioContext.resume();
      }
      outputStream=new MediaStream(tracks);
      recorder=new MediaRecorder(outputStream,{mimeType:mime,videoBitsPerSecond:3000000});
      const blobs=[];
      const finished=new Promise((resolve,reject)=>{
        recorder.addEventListener("dataavailable",event=>{if(event.data?.size)blobs.push(event.data);});
        recorder.addEventListener("error",event=>reject(event.error||Error("Browser recording failed.")),{once:true});
        recorder.addEventListener("stop",()=>resolve(),{once:true});
      });
      recorder.start(500);
      await video.play();
      tick=setInterval(()=>{
        if(video.currentTime>=c.end-.055||video.ended){
          if(recorder.state!=="inactive")recorder.stop();
          return;
        }
        if(video.readyState>=2)draw.drawImage(video,0,0,canvas.width,canvas.height);
        const progress=Math.round(Math.min(100,Math.max(0,(video.currentTime-c.start)/(c.end-c.start)*100)));
        status("Rendering clip "+part+"/"+total+" · "+progress+"% · Keep this tab open");
      },33);
      await finished;
      const blob=new Blob(blobs,{type:recorder.mimeType||mime});
      if(blob.size<1000)throw Error("Browser recorder returned an empty clip. Try another codec or browser.");
      return {blob,name:filename(c.name)+"."+extension};
    }finally{
      if(tick!==null)clearInterval(tick);
      if(recorder && recorder.state!=="inactive")recorder.stop();
      video.pause();
      if(outputStream)outputStream.getTracks().forEach(t=>t.stop());
      if(videoStream)videoStream.getTracks().forEach(t=>t.stop());
      if(audioContext)audioContext.close().catch(()=>{});
      video.removeAttribute("src");video.load();video.remove();
    }
  }
  const crcTable=(()=>{const t=[];for(let n=0;n<256;n++){let c=n;for(let j=0;j<8;j++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
  function crc32(bytes){let crc=0xffffffff;for(const byte of bytes)crc=crcTable[(crc^byte)&255]^(crc>>>8);return(crc^0xffffffff)>>>0;}
  function zipHeader(bytes,values){const v=new DataView(bytes.buffer);for(const [type,offset,value] of values)v[type](offset,value,true);return bytes;}
  async function zipClips(entries){
    const parts=[],central=[],encoder=new TextEncoder();let offset=0;
    for(const entry of entries){
      const name=encoder.encode(entry.name),data=new Uint8Array(await entry.blob.arrayBuffer());
      if(data.length>0xffffffff||offset+data.length>0xffffffff)throw Error("ZIP exceeds browser-safe size; download clips individually.");
      const crc=crc32(data),size=data.length;
      const head=zipHeader(new Uint8Array(30),[["setUint32",0,0x04034b50],["setUint16",4,20],["setUint16",8,0],["setUint16",10,0],["setUint32",14,crc],["setUint32",18,size],["setUint32",22,size],["setUint16",26,name.length]]);
      const directory=zipHeader(new Uint8Array(46),[["setUint32",0,0x02014b50],["setUint16",4,20],["setUint16",6,20],["setUint32",16,crc],["setUint32",20,size],["setUint32",24,size],["setUint16",28,name.length],["setUint32",42,offset]]);
      parts.push(head,name,data);central.push(directory,name);
      offset+=head.length+name.length+size;
    }
    const centralSize=central.reduce((sum,a)=>sum+a.length,0);
    const end=zipHeader(new Uint8Array(22),[["setUint32",0,0x06054b50],["setUint16",8,entries.length],["setUint16",10,entries.length],["setUint32",12,centralSize],["setUint32",16,offset]]);
    return new Blob([...parts,...central,end],{type:"application/zip"});
  }
  async function exportOne(c){
    if(exporting)return;
    exporting=true;render();player.pause();
    try {
      const result=await encodeClip(c,1,1);
      download(result.blob,result.name);
      status("Downloaded "+result.name+" · "+(result.blob.size/1024/1024).toFixed(1)+" MB");
    }catch(error){status("Export failed: "+error.message);}
    finally{exporting=false;render();}
  }
  $("clipExportAll").addEventListener("click",async()=>{
    if(exporting||!clips.length)return;
    exporting=true;render();player.pause();
    try {
      const entries=[];
      for(let i=0;i<clips.length;i++){
        const clip=await encodeClip(clips[i],i+1,clips.length);
        entries.push({...clip,name:String(i+1).padStart(2,"0")+"-"+clip.name});
        if(entries.reduce((n,x)=>n+x.blob.size,0)>320*1024*1024)throw Error("Output exceeds 320 MB. Download clips individually.");
      }
      status("Packaging "+entries.length+" clips in ZIP…");
      const zip=await zipClips(entries);
      download(zip,"viralforge-clips.zip");
      status("ZIP downloaded: "+entries.length+" separately playable clips.");
    }catch(error){status("Export failed: "+error.message);}
    finally{exporting=false;render();}
  });
  window.addEventListener("beforeunload",()=>{if(fileURL)URL.revokeObjectURL(fileURL);});
  render();
})();
