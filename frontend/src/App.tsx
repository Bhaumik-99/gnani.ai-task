import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Activity, ArrowLeft, AudioLines, CheckCircle2, ChevronRight, Headphones, Mic, MicOff, Phone, PhoneCall, PhoneOff, Shield, ShieldAlert, ShieldCheck, Volume2, VolumeX, Wifi } from "lucide-react";
import { createSession, getConfig, socketUrl, type SessionType, type ThreatPayload, type SessionLanguage } from "./api";
import { PcmStreamPlayer, startPcmCapture, stopMicrophone, type CaptureController } from "./audio/capture";

function Header() {
  return <header className="topbar"><Link className="brand" to="/"><span className="brand-icon"><ShieldCheck size={20}/></span><span>vaani<span className="brand-muted">shield</span></span></Link><span className="demo-chip"><i/> SIMULATED CALL DEMO</span></header>;
}

function Home() {
  const [config, setConfig] = useState<Awaited<ReturnType<typeof getConfig>> | null>(null);
  useEffect(() => { getConfig().then(setConfig).catch(() => setConfig(null)); }, []);
  return <main className="page">
    <section className="hero">
      <div className="eyebrow">REAL-TIME VOICE SECURITY</div>
      <h1>Your voice.<br/><span>Your protection.</span></h1>
      <p>Understand suspicious requests in Hindi and English, inspect the evidence, and try a separate conversational voice assistant.</p>
      <div className="hero-actions"><Link className="button primary" to="/scam-demo"><Phone size={17}/> Try scam simulation <ChevronRight size={17}/></Link><Link className="button secondary" to="/assistant"><AudioLines size={17}/> Talk to Vaani</Link></div>
      <div className="trust-row"><span><Shield size={14}/> Privacy-conscious demo</span><span><Wifi size={14}/> Gnani voice models</span></div>
    </section>
    <section className="feature-grid">
      <Link to="/scam-demo" className="feature-card"><div className="feature-icon red"><ShieldAlert/></div><small>01 / PROTECTION</small><h2>ScamShield</h2><p>Simulate a suspicious call and inspect transcripts, deterministic evidence and optional contextual risk analysis.</p><b>Open simulator <ChevronRight size={15}/></b></Link>
      <Link to="/assistant" className="feature-card"><div className="feature-icon violet"><AudioLines/></div><small>02 / CONVERSATION</small><h2>Vaani Assistant</h2><p>A separate Hinglish voice session using Prisma, self-hosted Evon and Timbre speech generation.</p><b>Start a conversation <ChevronRight size={15}/></b></Link>
    </section>
    <section className="model-strip"><div><small>GNANI MODEL STACK</small><h3>Built around Indian speech</h3></div><div className="models"><span><b>Prisma</b><small>STT · v3.0</small></span><span><b>Evon</b><small>Reasoning · v3.3</small></span><span><b>Timbre</b><small>TTS · v3.0</small></span></div></section>
    <section className="status-panel"><div><small>INTEGRATION STATUS</small><h3>Provider readiness</h3><p>{config?.note ?? "Backend status is unavailable."}</p></div><div className="provider-list">{config?.providers.map((item) => <div key={item.provider}><span>{item.provider} · {item.model}</span><strong className={item.configured ? "ready" : "pending"}>{item.configured ? "Configured" : "Not configured"}</strong></div>) ?? <span>Backend not connected</span>}</div></section>
    <footer>VaaniShield · Simulated call experience, not telecom call interception.</footer>
  </main>;
}

function CallScreen({ assistant = false }: { assistant?: boolean }) {
  const navigate = useNavigate();
  const sessionType: SessionType = assistant ? "assistant" : "scam_demo";
  const [phase, setPhase] = useState<"intro" | "incoming" | "active" | "ended">("intro");
  const [status, setStatus] = useState("Ready");
  const [seconds, setSeconds] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [partial, setPartial] = useState("");
  const [reply, setReply] = useState("");
  const [threat, setThreat] = useState<ThreatPayload | null>(null);
  const [phrase, setPhrase] = useState("Hello sir, main bank se bol raha hoon. Account block hone se bachane ke liye apna OTP bata dijiye.");
  const [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(false);
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const [sampleBusy, setSampleBusy] = useState(false);
  const [language, setLanguage] = useState<SessionLanguage>("hi-IN");
  const [providerConfig, setProviderConfig] = useState<Awaited<ReturnType<typeof getConfig>> | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | undefined>(undefined);
  const contextRef = useRef<AudioContext | undefined>(undefined);
  const captureRef = useRef<CaptureController | null>(null);
  const playerRef = useRef<PcmStreamPlayer | null>(null);
  const inputRateRef = useRef<8000 | 16000>(16000);
  const outputRateRef = useRef(24000);
  const endRequestedRef = useRef(false);
  const connectTimerRef = useRef<number | undefined>(undefined);
  const endTimerRef = useRef<number | undefined>(undefined);
  const captureStartingRef = useRef(false);
  const duration = useMemo(() => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`, [seconds]);

  useEffect(() => { getConfig().then(setProviderConfig).catch(() => setProviderConfig(null)).finally(() => setConfigLoading(false)); }, []);
  useEffect(() => {
    if (phase !== "active") return;
    const timer = window.setInterval(() => setSeconds(value => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  function cleanup() {
    captureRef.current?.stop();
    captureRef.current = null;
    captureStartingRef.current = false;
    stopMicrophone(streamRef.current);
    streamRef.current = undefined;
    playerRef.current?.stop();
    playerRef.current = null;
    const context = contextRef.current;
    contextRef.current = undefined;
    if (context && context.state !== "closed") void context.close();
  }

  useEffect(() => () => {
    if (connectTimerRef.current !== undefined) window.clearTimeout(connectTimerRef.current);
    if (endTimerRef.current !== undefined) window.clearTimeout(endTimerRef.current);
    const ws = socketRef.current;
    socketRef.current = null;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ event: "session.end", payload: {} }));
    ws?.close();
    cleanup();
  }, []);

  async function startCapture(ws: WebSocket) {
    const stream = streamRef.current;
    const context = contextRef.current;
    if (!stream || !context || captureRef.current || captureStartingRef.current || ws.readyState !== WebSocket.OPEN) return;
    captureStartingRef.current = true;
    try {
      const controller = await startPcmCapture(context, stream, frame => {
        if (ws.readyState !== WebSocket.OPEN) return;
        if (ws.bufferedAmount > 64 * 1024) {
          setStatus("Audio uplink congested. Session closed rather than silently dropping speech.");
          ws.close(1013, "Audio uplink congested");
          return;
        }
        ws.send(frame);
      }, inputRateRef.current);
      if (ws.readyState !== WebSocket.OPEN || endRequestedRef.current) controller.stop();
      else {
        captureRef.current = controller;
        setStatus("Prisma connected · microphone streaming");
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Microphone audio could not be initialized.");
      ws.close();
    } finally {
      captureStartingRef.current = false;
    }
  }

  async function acceptCall() {
    setBusy(true);
    setStatus("Checking provider configuration…");
    endRequestedRef.current = false;
    setMuted(false);
    setSpeakerMuted(false);
    setSeconds(0);
    setTranscript("");
    setPartial("");
    setReply("");
    setThreat(null);
    try {
      const config = await getConfig();
      setProviderConfig(config);
      if (assistant && !config.assistant_enabled) throw new Error("Vaani requires configured Prisma, a self-hosted Evon endpoint and Timbre.");
      inputRateRef.current = config.prisma_sample_rate === 8000 ? 8000 : 16000;
      const prismaReady = config.providers.some(provider => provider.provider === "prisma" && provider.configured);
      if (prismaReady) {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone capture is unavailable in this browser.");
        streamRef.current = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, noiseSuppression: false, echoCancellation: false, autoGainControl: false },
          video: false
        });
      }
      const session = await createSession(sessionType, language);
      const ws = new WebSocket(socketUrl(session.session_id), ["vaanishield.v1", `session.${session.token}`]);
      ws.binaryType = "arraybuffer";
      socketRef.current = ws;
      connectTimerRef.current = window.setTimeout(() => {
        if (ws.readyState === WebSocket.CONNECTING) {
          setStatus("Connection timed out. Please retry.");
          ws.close();
        }
      }, 12000);

      ws.onopen = async () => {
        if (connectTimerRef.current !== undefined) window.clearTimeout(connectTimerRef.current);
        try {
          if (streamRef.current) {
            const context = new AudioContext();
            contextRef.current = context;
            await context.resume();
            playerRef.current = new PcmStreamPlayer(context);
          }
          ws.send(JSON.stringify({ event: "session.start", payload: { language_code: "indic-auto", sample_rate: inputRateRef.current } }));
          setPhase("active");
          setStatus(prismaReady ? "Session connected · starting Prisma" : "Prisma not configured · use the fictional demo phrase");
          setBusy(false);
        } catch (error) {
          setStatus(error instanceof Error ? error.message : "Could not initialize voice session.");
          setBusy(false);
          ws.close();
          cleanup();
        }
      };

      ws.onmessage = message => {
        if (message.data instanceof ArrayBuffer) {
          const accepted = playerRef.current?.enqueuePcm16(message.data, outputRateRef.current);
          if (accepted === false) {
            playerRef.current?.stop();
            setStatus("Playback queue limit reached; audio cleared to recover.");
          }
          return;
        }
        let event: { event: string; payload: Record<string, unknown> };
        try { event = JSON.parse(String(message.data)); } catch { return; }
        const payload = event.payload ?? {};
        switch (event.event) {
          case "provider.status":
            if (payload.provider === "prisma" && payload.status === "connected") void startCapture(ws);
            else if (payload.provider === "prisma") {
              setStatus(payload.status === "not_configured" ? "Prisma not configured · fictional phrase test remains available" : "Prisma provider unavailable");
              if (payload.status !== "connecting") {
                stopMicrophone(streamRef.current);
                streamRef.current = undefined;
              }
            }
            break;
          case "transcript.partial":
            setPartial(String(payload.text ?? ""));
            break;
          case "transcript.final":
            setTranscript(current => current ? `${current}\n${String(payload.text ?? "")}` : String(payload.text ?? ""));
            setPartial("");
            setSampleBusy(false);
            break;
          case "threat.detected":
          case "threat.updated":
            setThreat(payload as unknown as ThreatPayload);
            break;
          case "analysis.status":
            setStatus(String(payload.reason ?? `Analysis: ${String(payload.mode ?? "complete")}`));
            break;
          case "assistant.message":
            setReply(String(payload.text ?? ""));
            break;
          case "assistant.error":
          case "provider.error":
          case "audio.output.error":
            setStatus(String(payload.message ?? "Voice service unavailable."));
            break;
          case "audio.output.start":
            outputRateRef.current = Number(payload.sample_rate ?? 24000);
            break;
          case "audio.output.end":
            setStatus("Response finished · listening");
            break;
          case "session.expired":
            endRequestedRef.current = true;
            setPhase("ended");
            setStatus("Session expired. Start a new session.");
            cleanup();
            ws.close();
            break;
          case "session.ended":
            endRequestedRef.current = true;
            if (endTimerRef.current !== undefined) window.clearTimeout(endTimerRef.current);
            setPhase("ended");
            setStatus("Session ended");
            cleanup();
            ws.close();
            break;
          case "error":
            setStatus(String(payload.message ?? "Session error"));
            break;
          default:
            break;
        }
      };
      ws.onerror = () => { setStatus("WebSocket connection error"); setBusy(false); cleanup(); };
      ws.onclose = () => {
        if (!endRequestedRef.current) {
          setStatus("Session disconnected. Start a new session to continue.");
          setPhase(current => current === "active" || current === "incoming" ? "ended" : current);
        }
        if (connectTimerRef.current !== undefined) window.clearTimeout(connectTimerRef.current);
        setBusy(false);
        cleanup();
      };
    } catch (error) {
      cleanup();
      setStatus(error instanceof Error ? error.message : "Unable to start session.");
      setBusy(false);
    }
  }

  function sendSample() {
    const ws = socketRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) { setStatus("Connect the demo session first."); return; }
    setSampleBusy(true);
    ws.send(JSON.stringify({ event: "transcript.demo", payload: { text: phrase } }));
  }
  function toggleMic() {
    const next = !muted;
    setMuted(next);
    streamRef.current?.getAudioTracks().forEach(track => { track.enabled = !next; });
    captureRef.current?.setMuted(next);
  }
  function toggleSpeaker() {
    const next = !speakerMuted;
    setSpeakerMuted(next);
    playerRef.current?.setMuted(next);
  }
  function interrupt() {
    socketRef.current?.send(JSON.stringify({ event: "assistant.interrupt", payload: {} }));
    playerRef.current?.stop();
    setReply("");
  }
  function endCall() {
    const ws = socketRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      endRequestedRef.current = true;
      ws.send(JSON.stringify({ event: "session.end", payload: {} }));
      setStatus("Ending session…");
      endTimerRef.current = window.setTimeout(() => {
        ws.close();
        cleanup();
        setPhase("ended");
        setStatus("Session closed locally after waiting for acknowledgement.");
      }, 3000);
    } else {
      cleanup();
      setPhase("ended");
      setStatus("Session ended");
    }
  }

  return <main className="call-page">
    <button className="back-button" onClick={() => navigate("/")}><ArrowLeft size={16}/> Back to home</button>
    {phase === "intro" && <section className="call-intro"><div className="intro-orb">{assistant ? <AudioLines size={34}/> : <ShieldAlert size={34}/>}</div><small>{assistant ? "VOICE CONVERSATION" : "SIMULATED INCOMING CALL"}</small><h1>{assistant ? "Talk to Vaani." : "Test your protection."}</h1><p>{assistant ? "Talk naturally in Hindi or English. Configure all three model services to enable live conversation." : "Start a simulated call, speak a fictional scenario, and inspect transcript and risk evidence."}</p><div className="permission-note"><Mic size={16}/> Microphone access is requested only when Prisma is configured and the session starts.</div><label className="language-picker">Speech language<select value={language} onChange={event => setLanguage(event.target.value as SessionLanguage)}><option value="hi-IN">Hindi</option><option value="en-IN">English</option></select></label>{assistant && !providerConfig?.assistant_enabled && <div className="permission-note">{configLoading ? "Checking provider readiness…" : "Configure Prisma, self-hosted Evon v3.3 and Timbre to enable voice conversations."}</div>}<button className="button primary" disabled={assistant && (configLoading || !providerConfig?.assistant_enabled)} onClick={() => setPhase("incoming")}>{assistant ? <Headphones size={17}/> : <PhoneCall size={17}/>} {assistant ? "Prepare voice session" : "Simulate incoming call"}</button></section>}
    {phase === "incoming" && <section className="phone-shell"><div className="phone-top"><span>VAANISHIELD DEMO</span><span>•••</span></div><div className="caller-avatar"><PhoneCall size={28}/></div><small>{assistant ? "VOICE ASSISTANT" : "INCOMING DEMO CALL"}</small><h2>{assistant ? "Vaani Assistant" : "Unknown Caller"}</h2><p>{assistant ? "Hinglish · AI voice session" : "Simulated caller · Not a real phone call"}</p><div className="incoming-actions"><button className="decline" onClick={() => setPhase("intro")}><PhoneOff/></button><button className="accept" disabled={busy} onClick={acceptCall}><Phone/></button></div><div className="action-labels"><span>Cancel</span><span>{busy ? "Connecting…" : "Accept"}</span></div><div className="status-text">{status}</div></section>}
    {phase === "active" && <section className={`phone-shell active-shell ${threat ? "alert-shell" : ""}`}><div className="phone-top"><span>{assistant ? "VAANI ASSISTANT" : "SCAMSHIELD"}</span><span className="live-dot"/></div><div className="active-caller"><div className="caller-avatar">{assistant ? <AudioLines size={28}/> : <Shield size={28}/>}</div><h2>{assistant ? "Vaani" : "Unknown Caller"}</h2><p>{duration} · {status}</p></div>
      {threat && !assistant ? <div className="threat-alert"><div><ShieldAlert size={18}/> SCAM CALL DETECTED</div><h3>Do not share sensitive information.</h3><p>{threat.warning_message}</p><p>{threat.explanation}</p><div className="threat-meta"><b>{threat.scam_type.replace(/_/g, " ")}</b><b>{threat.risk_level.toUpperCase()}</b></div>{threat.evidence.map((item, index) => <small key={index}>• {item.text} · {item.category}</small>)}</div> : <div className="wave-panel"><div className="wave-bars"><Activity size={28}/></div><span>{assistant ? "Listening · responses require Evon and Timbre" : "Live Prisma transcription when configured"}</span></div>}
      <div className="transcript"><small>TRANSCRIPT</small><p>{transcript || "Speak to receive a Prisma transcript."}{partial ? `\n… ${partial}` : ""}</p></div>
      {reply && <div className="transcript reply-panel"><small>VAANI RESPONSE</small><p>{reply}</p></div>}
      {!assistant && <div className="demo-input"><label htmlFor="demo-phrase">FICTIONAL DEMO PHRASE · LOCAL RULE TEST</label><textarea id="demo-phrase" value={phrase} onChange={e => setPhrase(e.target.value)}/><button disabled={sampleBusy} onClick={sendSample}>{sampleBusy ? "Analysing…" : "Analyse sample phrase"}</button></div>}
      <div className="call-controls"><button disabled={!streamRef.current} title={muted ? "Unmute microphone" : "Mute microphone"} onClick={toggleMic}>{muted ? <MicOff size={19}/> : <Mic size={19}/>}</button><button disabled={!playerRef.current} title={speakerMuted ? "Enable speaker" : "Mute speaker"} onClick={toggleSpeaker}>{speakerMuted ? <VolumeX size={19}/> : <Volume2 size={19}/>}</button>{assistant && <button title="Interrupt Vaani" onClick={interrupt}><Activity size={19}/></button>}<button className="hangup" title="End session" onClick={endCall}><PhoneOff size={20}/></button></div><span className="status-text">{status}</span>
    </section>}
    {phase === "ended" && <section className="ended-card"><CheckCircle2 size={34}/><h2>Session ended</h2><p>{threat ? "A suspicious request was flagged in this demo session." : "Your simulated session has finished."}</p>{threat && <div className="threat-meta"><b>{threat.scam_type}</b><b>{threat.risk_level}</b></div>}<button className="button primary" onClick={() => { endRequestedRef.current = false; setPhase("intro"); setSeconds(0); setTranscript(""); setPartial(""); setReply(""); setThreat(null); setStatus("Ready"); setSampleBusy(false); }}>Start again</button></section>}
  </main>;
}

export default function App() {
  return <><Header/><Routes><Route path="/" element={<Home/>}/><Route path="/scam-demo" element={<CallScreen/>}/><Route path="/assistant" element={<CallScreen assistant/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></>;
}
