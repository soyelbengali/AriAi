/* =====================================================
   ARIAI — SYSTEM PRIME  |  gui/script.js
   Wires the HTML to the Python pywebview API bridge.
   Mirrors the React app's feature set 1-to-1.
   ===================================================== */

/* -------------------------------------------------------
   BACKEND BRIDGE
   When run via python main.py, window.pywebview.api exists.
   When the HTML is opened directly in a browser it falls
   back to a thin in-memory stub so the UI still renders.
------------------------------------------------------- */
let backendMode = null; // 'python' | 'memory'

const memStore = {
  logs: [
    {
      id: "log-init", timestamp: "", command: "System Ignition Sequence Complete",
      spoken_text: "All subroutines loaded, sir. Ari mainframe is online.",
      markdown_text: "### Ari Sub-System AriAI Prime Active\n\nWelcome back, sir.\n\nType a command or press the holographic microphone to dictate tasks or search parameters.",
      google_search_performed: false, grounding_sources: [], actions_executed: [],
    }
  ],
  settings: {
    llm: { base_url:"https://api.openai.com/v1", api_key:"", model:"gpt-4o-mini" },
    embeddings: { base_url:"https://api.openai.com/v1", api_key:"", model:"text-embedding-3-small" },
    stt: { model:"nvidia/canary-180m-flash", device:"cpu", record_seconds:6, samplerate:16000 },
    tts: { provider:"puter", voice:"Joanna", piper_model:"en_US-lessac-medium" },
    search: { enabled:true, ollama_api_key:"", parallel_api_key:"", max_results:5 },
    conversation: { enabled:true, window_seconds:5 },
    voice_output_enabled:true, voice_input_enabled:true,
  },
};

function detectBackend() {
  return new Promise(resolve => {
    if (window.pywebview && window.pywebview.api) { backendMode = 'python'; return resolve(); }
    let done = false;
    window.addEventListener('pywebviewready', () => {
      if (done) return; done = true; backendMode = 'python'; resolve();
    });
    setTimeout(() => {
      if (done) return; done = true; backendMode = 'memory';
      console.info('AriAI: no pywebview bridge — running in-memory mode.');
      resolve();
    }, 600);
  });
}

const api = {
  getLogs:             ()       => backendMode==='python' ? window.pywebview.api.get_logs()              : Promise.resolve(memStore.logs),
  clearLogs:           ()       => backendMode==='python' ? window.pywebview.api.clear_logs()            : Promise.resolve(memStore.logs),
  getSettings:         ()       => backendMode==='python' ? window.pywebview.api.get_settings()          : Promise.resolve(memStore.settings),
  saveSettings:        (s)      => backendMode==='python' ? window.pywebview.api.save_settings(s) : Promise.resolve(deepMerge(memStore.settings,s)),
  executeCommand:      (cmd)    => backendMode==='python' ? window.pywebview.api.execute_command(cmd)    : Promise.resolve({queued:true}),
  startListening:      ()       => backendMode==='python' ? window.pywebview.api.start_listening()       : Promise.resolve({started:true}),
  speakText:           (t)      => backendMode==='python' ? window.pywebview.api.speak_text(t)           : Promise.resolve({ok:true}),
  getVoiceAvailability:() => backendMode==='python' ? window.pywebview.api.get_voice_availability()     : Promise.resolve({available:false,reason:'Browser mode'}),
  listLlmModels:       ()       => backendMode==='python' ? window.pywebview.api.list_llm_models()       : Promise.resolve([]),
  listEmbedModels:     ()       => backendMode==='python' ? window.pywebview.api.list_embedding_models() : Promise.resolve([]),
};

function deepMerge(base, override) {
  const out = Object.assign({}, base);
  for (const k in override) {
    if (override[k] && typeof override[k]==='object' && !Array.isArray(override[k]) && typeof out[k]==='object') {
      out[k] = deepMerge(out[k], override[k]);
    } else {
      out[k] = override[k];
    }
  }
  return out;
}

/* -------------------------------------------------------
   MARKDOWN RENDERER (simple inline)
------------------------------------------------------- */
function renderMarkdown(md) {
  if (!md) return '';
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let html = '';
  const lines = md.split('\n');
  let inUl = false;
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    if (line.startsWith('### ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h3>${esc(line.slice(4))}</h3>`;
    } else if (line.startsWith('## ')) {
      if (inUl) { html += '</ul>'; inUl = false; }
      html += `<h2>${esc(line.slice(3))}</h2>`;
    } else if (line.startsWith('* ') || line.startsWith('- ')) {
      if (!inUl) { html += '<ul>'; inUl = true; }
      html += `<li>${inlineMarkdown(esc(line.slice(2)))}</li>`;
    } else {
      if (inUl) { html += '</ul>'; inUl = false; }
      const p = line.trim();
      if (p) html += `<p>${inlineMarkdown(esc(p))}</p>`;
    }
  }
  if (inUl) html += '</ul>';
  return html;
}

function inlineMarkdown(s) {
  return s
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.*?)__/g,     '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g,     '<em>$1</em>')
    .replace(/_(.*?)_/g,       '<em>$1</em>')
    .replace(/`(.*?)`/g,       '<code>$1</code>');
}

/* -------------------------------------------------------
   TYPEWRITER EFFECT
------------------------------------------------------- */
function typewrite(containerEl, html, onDone) {
  containerEl.innerHTML = '';
  const tmp = document.createElement('div');
  tmp.innerHTML = html;

  const plainText = tmp.textContent || '';
  let charIdx = 0;
  const speed = Math.max(5, Math.min(22, 3000 / (plainText.length || 1)));

  function tick() {
    if (charIdx > plainText.length) {
      containerEl.innerHTML = html + '<span class="cursor-blink"></span>';
      setTimeout(() => {
        const cur = containerEl.querySelector('.cursor-blink');
        if (cur) cur.remove();
        if (onDone) onDone();
      }, 800);
      return;
    }
    containerEl.textContent = plainText.slice(0, charIdx);
    charIdx++;
    setTimeout(tick, speed);
  }
  tick();
}

/* -------------------------------------------------------
   STATUS / HUD
------------------------------------------------------- */
let currentStatus = 'idle';
let latestResult  = null;
let voiceEnabled  = true;
let ttsProvider   = 'puter';

function setHudStatus(status) {
  currentStatus = status;
  const hud = document.getElementById('ariHud');
  const statusEl = document.getElementById('coreStatus');
  const quoteEl  = document.getElementById('coreQuote');
  const micLabel = document.getElementById('micLabel');
  const micIcon  = document.getElementById('micIcon');
  const arc      = document.getElementById('hudArc');

  // remove all status classes
  hud.className = hud.className.replace(/\bhud-\w+/g, '').trim();

  const statusMap = {
    idle:      { cls:'hud-idle',   text:'ARI CORE ONLINE — AWAITING SIR\'S INPUT', label:'INSTRUCT', arc:'250 15', offset:'0' },
    loading:   { cls:'hud-loading',text:'INITIALIZING CANARY STT...',             label:'LOADING STT', arc:'120 145', offset:'0' },
    listening: { cls:'hud-listen', text:'ARI IS LISTENING...',                       label:'LISTENING', arc:'200 15', offset:'30' },
    thinking:  { cls:'hud-think',  text:'RESOLVING MAIN DATA CORRELATION...',           label:'CORRELATING', arc:'250 15', offset:'200' },
    speaking:  { cls:'hud-speak',  text:'ARI TRANSMITTING VOCAL...',                 label:'SPEAKING', arc:'250 15', offset:'0' },
    error:     { cls:'hud-error',  text:'SYSTEM INTEGRITY CORRUPTED',                   label:'ERROR', arc:'250 15', offset:'0' },
  };

  const cfg = statusMap[status] || statusMap.idle;
  hud.classList.add(cfg.cls);
  statusEl.textContent = cfg.text;
  micLabel.textContent = cfg.label;

  arc.setAttribute('stroke-dasharray', cfg.arc);
  arc.setAttribute('stroke-dashoffset', cfg.offset);

  // update mic icon
  const icons = {
    idle: `<rect x="9" y="2" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0"/><line x1="12" y1="18" x2="12" y2="22"/>`,
    loading: `<circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.5" stroke-dasharray="20 10"/>`,
    listening: `<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4"/><path d="M8 12h8M10 9h4M10 15h4"/>`,
    thinking: `<path d="M12 2a10 10 0 0 1 0 20" stroke-linecap="round"/>`,
    speaking: `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"/>`,
    error: `<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r="0.5" fill="currentColor"/>`,
  };
  micIcon.innerHTML = icons[status] || icons.idle;
  if (status === 'thinking' || status === 'loading') micIcon.classList.add('spin');
  else micIcon.classList.remove('spin');

  // ripple rings
  document.querySelectorAll('.hud-ripple').forEach(el => el.remove());
  const ringWrap = document.getElementById('hudRingWrap');
  if (status === 'listening') {
    for (let i = 0; i < 2; i++) {
      const r = document.createElement('div');
      r.className = 'hud-ripple';
      r.style.cssText = `border-color:rgba(52,211,153,.25);animation-delay:${i*0.7}s;animation-duration:${1.5+i*0.8}s;`;
      ringWrap.appendChild(r);
    }
  }
  if (status === 'speaking') {
    const r = document.createElement('div');
    r.className = 'hud-ripple';
    r.style.cssText = 'border-color:rgba(165,180,252,.15);animation-duration:2s;';
    ringWrap.appendChild(r);
  }

  // quote
  const quoteMap = {
    idle:      '"Awaiting command, sir. Press central core or provide instruction."',
    loading:   '"Warming up Canary speech recognition. This may take a moment."',
    listening: '"Go ahead, sir. I\'m listening."',
    thinking:  '"Processing your directive, sir. One moment."',
    speaking:  '"Transmitting, sir."',
    error:     '"I apologise, sir. A system error occurred."',
  };
  quoteEl.textContent = quoteMap[status] || quoteMap.idle;
}

/* voice push-back callbacks from Python */
window.onVoiceStatus = setHudStatus;
window.onVoiceResult = function(text) {
  setHudStatus('thinking');
  executeCommand(text);
};
window.onVoiceError = function(msg) {
  setHudStatus('error');
  const quoteEl = document.getElementById('coreQuote');
  if (quoteEl) quoteEl.textContent = `"Voice input failed: ${msg || 'unknown error'}"`;
  setTimeout(() => setHudStatus('idle'), 3000);
  console.warn('Voice error:', msg);
};

/* AI result callback from Python (via evaluate_js) */
window.onAriStatus = setHudStatus;
window.onAriResult = function(payload) {
  if (typeof payload === 'string') {
    try { payload = JSON.parse(payload); } catch(e) { return; }
  }
  latestResult = payload;
  setHudStatus('idle');

  const md    = payload.markdownText   || '';
  const spoke = payload.spokenText     || '';
  const sources = payload.groundingSources || [];
  const searched = payload.searchPerformed || payload.googleSearchPerformed || false;
  const actions  = payload.actionsExecuted || [];

  renderConsoleResponse(md, spoke, searched, sources, actions);
  loadLogs();

  // expand button becomes visible once there's content
  document.getElementById('expandResponseBtn').style.display = 'flex';

  // if command was from palette, close it
  closeCommandPalette();

  // speak in browser-mode (python mode speaks natively via pyttsx3)
  if (backendMode === 'memory' && voiceEnabled && spoke) {
    browserSpeak(spoke);
  }
};

/* -------------------------------------------------------
   CONSOLE RESPONSE
------------------------------------------------------- */
function renderConsoleResponse(md, spokenText, searched, sources, actions) {
  const empty  = document.getElementById('consoleEmpty');
  const mdEl   = document.getElementById('consoleMarkdown');
  const thinkB = document.getElementById('thinkingBanner');
  const searchB= document.getElementById('searchBanner');
  const searchL= document.getElementById('searchBannerLabel');
  const gSec   = document.getElementById('groundingSection');
  const gList  = document.getElementById('groundingList');
  const gCount = document.getElementById('groundingCount');

  thinkB.style.display = 'none';
  empty.style.display  = 'none';
  mdEl.style.display   = 'block';

  // search badge
  if (searched || sources.length) {
    searchL.textContent = sources.length ? `WEB GROUNDING ACTIVE — ${sources.length} CITATIONS` : 'WEB GROUNDING ACTIVE';
    searchB.style.display = 'inline-flex';
  } else {
    searchB.style.display = 'none';
  }

  // append actions note to markdown
  let fullMd = md;
  if (actions && actions.length) {
    fullMd += '\n\n## Actions Executed\n' + actions.map(a => `* ${a}`).join('\n');
  }

  const html = renderMarkdown(fullMd);
  typewrite(mdEl, html, null);

  // grounding sources
  if (sources.length) {
    gCount.textContent = sources.length;
    gList.innerHTML = sources.map((s, i) => `
      <a href="${s.uri || '#'}" class="grounding-link" target="_blank" rel="noopener">
        <span class="link-title">[${i+1}] ${escHtml(s.title || s.uri || 'Source')}</span>
        <svg class="link-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </a>`).join('');
    gSec.style.display = 'block';
  } else {
    gSec.style.display = 'none';
  }
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* -------------------------------------------------------
   EXECUTE COMMAND
------------------------------------------------------- */
function executeCommand(cmd) {
  if (!cmd || !cmd.trim()) return;

  // update console immediately to show thinking state
  const thinkB  = document.getElementById('thinkingBanner');
  const searchB  = document.getElementById('searchBanner');
  const empty    = document.getElementById('consoleEmpty');
  const mdEl     = document.getElementById('consoleMarkdown');

  thinkB.style.display   = 'inline-flex';
  searchB.style.display  = 'none';
  empty.style.display    = 'none';
  mdEl.style.display     = 'none';
  setHudStatus('thinking');

  if (backendMode === 'memory') {
    // In browser mode simulate a stub response
    setTimeout(() => {
      window.onAriResult({
        spokenText: 'Running in memory mode, sir. Connect via python main.py for full AI capability.',
        markdownText: '### Memory Mode Active\n\nNo Python bridge is connected. Run `python main.py` for full AI, voice, and web grounding features.',
        searchPerformed: false, groundingSources: [], actionsExecuted: [],
      });
    }, 1200);
    return;
  }

  api.executeCommand(cmd.trim()).catch(err => {
    setHudStatus('error');
    setTimeout(() => setHudStatus('idle'), 4000);
    console.error('Execute command error:', err);
  });
}

/* -------------------------------------------------------
   COMMAND HISTORY LOGS
------------------------------------------------------- */
function loadLogs() {
  return api.getLogs().then(renderLogs).catch(console.error);
}

function renderLogs(logs) {
  const listEl   = document.getElementById('historyList');
  const clearBtn = document.getElementById('clearLogsBtn');
  clearBtn.style.display = (logs && logs.length > 1) ? 'inline' : 'none';
  listEl.innerHTML = (logs || []).map(log => `
    <div class="history-item" data-log-id="${escHtml(log.id||'')}">
      <span class="history-text">${escHtml(log.command||'')}</span>
      <span class="history-time">${log.timestamp||'—'}</span>
    </div>`).join('');

  listEl.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('click', () => {
      // restore response from that log entry — match by unique id, not command text
      const logEntry = (logs||[]).find(l => l.id===item.dataset.logId);
      if (logEntry) {
        renderConsoleResponse(
          logEntry.markdown_text, logEntry.spoken_text,
          logEntry.google_search_performed,
          logEntry.grounding_sources||[], logEntry.actions_executed||[]
        );
        openResponseModal(
          logEntry.markdown_text, logEntry.spoken_text,
          logEntry.google_search_performed, logEntry.grounding_sources||[]
        );
      }
    });
  });
}

/* -------------------------------------------------------
   RESPONSE MODAL (expanded view)
------------------------------------------------------- */
function openResponseModal(md, spoken, searched, sources) {
  const modal   = document.getElementById('responseModal');
  const mdEl    = document.getElementById('modalMarkdown');
  const searchB = document.getElementById('modalSearchBanner');
  const searchL = document.getElementById('modalSearchBannerLabel');
  const gSec    = document.getElementById('modalGrounding');
  const gList   = document.getElementById('modalGroundingList');
  const gCount  = document.getElementById('modalGroundingCount');

  if (searched || (sources && sources.length)) {
    searchL.textContent = sources && sources.length ? `WEB GROUNDING ACTIVE — ${sources.length} CITATIONS` : 'WEB GROUNDING ACTIVE';
    searchB.style.display = 'inline-flex';
  } else {
    searchB.style.display = 'none';
  }

  mdEl.innerHTML = renderMarkdown(md || '');

  if (sources && sources.length) {
    gCount.textContent = sources.length;
    gList.innerHTML = sources.map((s,i) => `
      <a href="${s.uri||'#'}" class="grounding-link" target="_blank" rel="noopener">
        <span class="link-title">[${i+1}] ${escHtml(s.title||s.uri||'Source')}</span>
        <svg class="link-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </a>`).join('');
    gSec.style.display = 'block';
  } else {
    gSec.style.display = 'none';
  }

  modal.classList.add('open');

  // wire "Read Aloud" in modal
  document.getElementById('modalReadAloud').onclick = () => {
    if (spoken) api.speakText(spoken);
  };
}

function closeResponseModal() {
  document.getElementById('responseModal').classList.remove('open');
}

/* -------------------------------------------------------
   SETTINGS / AI CORES DRAWER
------------------------------------------------------- */
function loadSettings() {
  api.getSettings().then(cfg => {
    const llm = cfg.llm || {}, emb = cfg.embeddings || {}, stt = cfg.stt || {};
    const tts = cfg.tts || {}, srch = cfg.search || {}, conv = cfg.conversation || {};

    document.getElementById('llmBaseUrlInput').value   = llm.base_url || '';
    document.getElementById('llmApiKeyInput').value    = llm.api_key || '';
    document.getElementById('llmModelInput').value     = llm.model || '';

    document.getElementById('embedBaseUrlInput').value = emb.base_url || '';
    document.getElementById('embedApiKeyInput').value  = emb.api_key || '';
    document.getElementById('embedModelInput').value   = emb.model || '';

    document.getElementById('sttSecondsInput').value   = stt.record_seconds || 6;
    document.getElementById('conversationSecondsInput').value = conv.window_seconds || 5;
    document.getElementById('conversationToggle').checked = conv.enabled !== false;

    document.getElementById('ttsProviderInput').value  = tts.provider || 'puter';
    document.getElementById('ttsVoiceInput').value     = tts.voice || 'Joanna';
    document.getElementById('piperModelInput').value   = tts.piper_model || 'en_US-lessac-medium';

    document.getElementById('searchToggle').checked           = srch.enabled !== false;
    document.getElementById('ollamaSearchKeyInput').value      = srch.ollama_api_key || '';
    document.getElementById('parallelSearchKeyInput').value    = srch.parallel_api_key || '';

    document.getElementById('voiceOutputToggle').checked = !!cfg.voice_output_enabled;
    document.getElementById('voiceInputToggle').checked  = !!cfg.voice_input_enabled;
    voiceEnabled = !!cfg.voice_output_enabled;
    ttsProvider = tts.provider || 'puter';
  }).catch(console.error);
}

function populateModelList(datalistId, models) {
  const dl = document.getElementById(datalistId);
  if (!dl) return;
  dl.innerHTML = (models || []).map(m => `<option value="${escHtml(m)}"></option>`).join('');
}

function saveCoresSettings() {
  const saveButton = document.getElementById('coresSave');
  const hint = document.getElementById('coresHint');
  if (saveButton.disabled) return;
  const payload = {
    llm: {
      base_url: document.getElementById('llmBaseUrlInput').value.trim(),
      api_key:  document.getElementById('llmApiKeyInput').value.trim(),
      model:    document.getElementById('llmModelInput').value.trim(),
    },
    embeddings: {
      base_url: document.getElementById('embedBaseUrlInput').value.trim(),
      api_key:  document.getElementById('embedApiKeyInput').value.trim(),
      model:    document.getElementById('embedModelInput').value.trim(),
    },
    stt: {
      record_seconds: parseInt(document.getElementById('sttSecondsInput').value, 10) || 6,
    },
    conversation: {
      enabled: document.getElementById('conversationToggle').checked,
      window_seconds: parseInt(document.getElementById('conversationSecondsInput').value, 10) || 5,
    },
    tts: {
      provider: document.getElementById('ttsProviderInput').value,
      voice: document.getElementById('ttsVoiceInput').value.trim() || 'Joanna',
      piper_model: document.getElementById('piperModelInput').value.trim() || 'en_US-lessac-medium',
    },
    search: {
      enabled: document.getElementById('searchToggle').checked,
      ollama_api_key:   document.getElementById('ollamaSearchKeyInput').value.trim(),
      parallel_api_key: document.getElementById('parallelSearchKeyInput').value.trim(),
    },
    voice_output_enabled: document.getElementById('voiceOutputToggle').checked,
    voice_input_enabled:  document.getElementById('voiceInputToggle').checked,
  };

  saveButton.disabled = true;
  saveButton.textContent = 'Locking core…';
  hint.textContent = 'Saving configuration…';
  hint.className = 'cores-hint is-pending';

  api.saveSettings(payload).then(() => {
    voiceEnabled = payload.voice_output_enabled;
    ttsProvider = payload.tts.provider;
    hint.className = 'cores-hint is-success';
    hint.textContent = '✓ Core configuration locked successfully.';
    setTimeout(() => { hint.textContent=''; hint.className='cores-hint'; }, 3000);
  }).catch(err => {
    document.getElementById('coresHint').textContent = '⚠ Save failed: ' + err;
    hint.className = 'cores-hint is-error';
  }).finally(() => {
    saveButton.disabled = false;
    saveButton.textContent = 'Verify & Lock Core';
  });
}

/* -------------------------------------------------------
   COMMAND PALETTE
------------------------------------------------------- */
function openCommandPalette() {
  const overlay = document.getElementById('commandOverlay');
  const inp = document.getElementById('commandInput');
  overlay.classList.add('open');
  inp.value = '';
  setTimeout(() => inp.focus(), 10);
}
function closeCommandPalette() {
  document.getElementById('commandOverlay').classList.remove('open');
}

/* -------------------------------------------------------
   BROWSER-MODE SPEECH SYNTHESIS (fallback)
------------------------------------------------------- */
function browserSpeak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const cleaned = text.replace(/[#*`_\[\]()\-+]/g,' ').replace(/\s+/g,' ').trim();
  const utt = new SpeechSynthesisUtterance(cleaned);
  utt.lang = 'en-US'; utt.pitch = 0.92; utt.rate = 1.05;
  const voices = window.speechSynthesis.getVoices();
  const maleKw = ['male','daniel','george','david','mark','james','richard','guy'];
  const femKw  = ['female','hazel','zira','susan','heera','zira','samantha','victoria'];
  let best = null, bestScore = -9999;
  voices.forEach(v => {
    const n = v.name.toLowerCase();
    if (!v.lang.toLowerCase().startsWith('en')) return;
    let s = 0;
    if (maleKw.some(k => n.includes(k))) s += 200;
    if (femKw.some(k => n.includes(k)))  s -= 300;
    if (v.lang.toLowerCase().startsWith('en-gb')) s += 100;
    if (s > bestScore) { bestScore = s; best = v; }
  });
  if (best) { utt.voice = best; utt.lang = best.lang; }
  window.speechSynthesis.speak(utt);
}

async function speakWithPuter(text) {
  const cleaned = (text || '').replace(/[#*`_\[\]()\-+]/g, ' ').replace(/\s+/g, ' ').trim();
  if (!cleaned) return;

  try {
    if (!window.puter || !window.puter.ai || !window.puter.ai.txt2speech) {
      throw new Error('Puter TTS is unavailable');
    }
    const voiceInput = document.getElementById('ttsVoiceInput');
    const configuredVoice = voiceInput && voiceInput.value.trim();
    const voice = configuredVoice && !configuredVoice.includes('Jenny') ? configuredVoice : 'Joanna';
    setHudStatus('speaking');
    const audio = await window.puter.ai.txt2speech(cleaned, {
      voice,
      engine: 'neural',
      language: 'en-US',
    });
    audio.onended = () => setHudStatus('idle');
    await audio.play();
  } catch (error) {
    console.warn('Puter TTS failed; using browser speech synthesis instead.', error);
    browserSpeak(cleaned);
    setHudStatus('idle');
  }
}

window.onAriSpeak = text => {
  if (voiceEnabled && ttsProvider === 'puter') speakWithPuter(text);
};

/* -------------------------------------------------------
   DOM READY
------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {

  // --- clock ---
  const clockEl = document.getElementById('clock');
  function tick() {
    const n=new Date(), p=n=>String(n).padStart(2,'0');
    clockEl.textContent = `${p(n.getHours())}:${p(n.getMinutes())}:${p(n.getSeconds())}`;
  }
  tick(); setInterval(tick, 1000);

  // --- initial HUD state ---
  setHudStatus('idle');

  // --- AI Cores drawer ---
  const coresBtn     = document.getElementById('coresBtn');
  const coresOverlay = document.getElementById('coresOverlay');
  const coresClose   = document.getElementById('coresClose');
  const coresSave    = document.getElementById('coresSave');

  function openCoresModal() {
    coresOverlay.classList.add('open');
    coresBtn.classList.add('active');
    loadSettings();
  }
  function closeCoresModal() {
    coresOverlay.classList.remove('open');
    coresBtn.classList.remove('active');
  }

  coresBtn.addEventListener('click', openCoresModal);
  coresClose.addEventListener('click', closeCoresModal);
  coresOverlay.addEventListener('click', e => {
    if (e.target === coresOverlay) closeCoresModal();
  });
  coresSave.addEventListener('click', saveCoresSettings);

  document.querySelectorAll('.cores-tab').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      document.querySelectorAll('.cores-tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.cores-tabpanel').forEach(p => p.classList.remove('active'));
      tabBtn.classList.add('active');
      const panel = document.getElementById(`tab-${tabBtn.dataset.tab}`);
      panel.classList.add('active');
      panel.scrollTop = 0;
    });
  });

  document.getElementById('llmModelRefreshBtn').addEventListener('click', () => {
    api.listLlmModels().then(models => populateModelList('llmModelList', models)).catch(console.error);
  });
  document.getElementById('embedModelRefreshBtn').addEventListener('click', () => {
    api.listEmbedModels().then(models => populateModelList('embedModelList', models)).catch(console.error);
  });

  // --- command palette ---
  document.getElementById('summonBtn').addEventListener('click', openCommandPalette);
  document.getElementById('commandOverlay').addEventListener('click', e => {
    if (e.target===document.getElementById('commandOverlay')) closeCommandPalette();
  });

  document.querySelectorAll('.pill[data-fill]').forEach(pill => {
    pill.addEventListener('click', () => {
      document.getElementById('commandInput').value = pill.dataset.fill;
      document.getElementById('commandInput').focus();
    });
  });

  const transmitBtn  = document.getElementById('transmitBtn');
  const transmitLbl  = document.getElementById('transmitLabel');
  const transmitSpin = document.getElementById('transmitSpin');

  function transmitCommand() {
    const cmd = document.getElementById('commandInput').value.trim();
    if (!cmd) return;
    transmitBtn.disabled = true;
    transmitLbl.textContent = 'TRANSMITTING…';
    transmitSpin.style.display = 'inline';
    executeCommand(cmd);
    // re-enable after a short window (result arrives via onAriResult callback)
    setTimeout(() => {
      transmitBtn.disabled = false;
      transmitLbl.textContent = 'TRANSMIT COMMAND';
      transmitSpin.style.display = 'none';
      closeCommandPalette();
    }, 1500);
  }

  transmitBtn.addEventListener('click', transmitCommand);
  document.getElementById('commandInput').addEventListener('keydown', e => {
    if (e.key==='Enter') { e.preventDefault(); transmitCommand(); }
  });

  // "/" key opens palette
  document.addEventListener('keydown', e => {
    if (e.key !== '/') return;
    const active = document.activeElement;
    const typing = active && (active.tagName==='INPUT'||active.tagName==='TEXTAREA');
    if (typing || document.getElementById('commandOverlay').classList.contains('open')) return;
    e.preventDefault(); openCommandPalette();
  });
  document.addEventListener('keydown', e => {
    if (e.key==='Escape') { closeCommandPalette(); closeResponseModal(); document.getElementById('coresOverlay').classList.remove('open'); document.getElementById('coresBtn').classList.remove('active'); }
  });

  // --- mic button ---
  document.getElementById('micBtn').addEventListener('click', () => {
    if (currentStatus === 'loading') return;
    if (currentStatus === 'listening') {
      setHudStatus('idle');
      return;
    }
    if (backendMode === 'python') {
      api.startListening().catch(err => window.onVoiceError(err && err.message ? err.message : String(err)));
    } else {
      // browser fallback
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { alert('Speech recognition not supported. Run via python main.py or use Chrome.'); return; }
      setHudStatus('listening');
      const rec = new SR();
      rec.lang = 'en-US'; rec.continuous = false; rec.interimResults = false;
      rec.onresult = ev => { const t=ev.results[0][0].transcript; if(t) { window.onVoiceResult(t); } };
      rec.onerror  = () => { setHudStatus('error'); setTimeout(()=>setHudStatus('idle'),3000); };
      rec.onend    = () => { if(currentStatus==='listening') setHudStatus('idle'); };
      rec.start();
    }
  });

  // --- vocal toggle ---
  const vocalBtn   = document.getElementById('vocalBtn');
  const vocalLabel = document.getElementById('vocalLabel');
  vocalBtn.addEventListener('click', () => {
    voiceEnabled = !voiceEnabled;
    vocalLabel.textContent = voiceEnabled ? 'VOCAL ACTIVE' : 'VOCAL MUTED';
    vocalBtn.classList.toggle('muted', !voiceEnabled);
    api.saveSettings({ voice_output_enabled: voiceEnabled }).catch(()=>{});
  });

  // --- clear logs ---
  document.getElementById('clearLogsBtn').addEventListener('click', () => {
    api.clearLogs().then(loadLogs).catch(console.error);
  });

  // --- expand response modal ---
  document.getElementById('expandResponseBtn').addEventListener('click', () => {
    if (!latestResult) return;
    openResponseModal(
      latestResult.markdownText, latestResult.spokenText,
      latestResult.searchPerformed || latestResult.googleSearchPerformed,
      latestResult.groundingSources || []
    );
  });
  document.getElementById('consoleMarkdown').addEventListener('click', () => {
    if (!latestResult) return;
    openResponseModal(
      latestResult.markdownText, latestResult.spokenText,
      latestResult.searchPerformed || latestResult.googleSearchPerformed,
      latestResult.groundingSources || []
    );
  });

  // --- response modal close ---
  document.getElementById('responseModalClose').addEventListener('click', closeResponseModal);
  document.getElementById('responseModalAck').addEventListener('click', closeResponseModal);
  document.getElementById('responseModal').addEventListener('click', e => {
    if (e.target===document.getElementById('responseModal')) closeResponseModal();
  });

  // --- boot sequence ---
  detectBackend().then(() => {
    return Promise.all([loadLogs(), loadSettings()]);
  });

});
