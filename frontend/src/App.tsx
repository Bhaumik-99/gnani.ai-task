import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Activity, ArrowLeft, AudioLines, CheckCircle2, ChevronRight, Headphones, Mic, Phone, PhoneCall, PhoneOff, Shield, ShieldAlert, ShieldCheck, Volume2, Wifi } from "lucide-react";
import { createSession, getConfig, socketUrl, type ThreatPayload } from "./api";
import { encodePcm16, requestRawMicrophone, stopMicrophone } from "./audio";

type Provider = { provider: string; model: string; configured: boolean };
type PublicConfig = { providers: Provider[]; live_inference_enabled: boolean; note: string };

function Header() {
  return <header className="topbar"><Link className="brand" to="/"><span className="brand-icon"><ShieldCheck size={20}/></span><span>vaani<span className="brand-muted">shield</span></span></Link><span className="demo-chip"><i/> DEMO ENVIRONMENT</span></header>;
}

function Home() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  useEffect(() => { getConfig().then(setConfig).catch(() => setConfig(null)); }, []);
  return <main className="page">
    <section className="hero">
      <div className="eyebrow">REAL-TIME VOICE INTELLIGENCE</div>
      <h1>Your voice.<br/><span>Your protection.</span></h1>
      <p>A voice-first safety experience for conversations. Detect suspicious requests, understand Hinglish, and talk naturally with your AI assistant.</p>
      <div className="hero-actions"><Link className="button primary" to="/scam-demo"><Phone size={17}/> Try scam simulation <ChevronRight size={17}/></Link><Link className="button secondary" to="/assistant"><AudioLines size={17}/> Talk to Vaani</Link></div>
      <div className="trust-row"><span><Shield size={14}/> Privacy-conscious demo</span><span><Wifi size={14}/> Gnani integration scaffold</span></div>
    </section>
    <section className="feature-grid">
      <Link to="/scam-demo" className="feature-card"><div className="feature-icon red"><ShieldAlert/></div><small>01 / PROTECTION</small><h2>ScamShield</h2><p>Simulate an incoming suspicious call, speak a fictional scam phrase and inspect the threat evidence.</p><b>Open simulator <ChevronRight size={15}/></b></Link>
      <Link to="/assistant" className="feature-card"><div className="feature-icon violet"><AudioLines/></div><small>02 / CONVERSATION</small><h2>Vaani Assistant</h2><p>A separate Hinglish voice session interface, designed for streaming speech and interruption-aware conversations.</p><b>Start a conversation <ChevronRight size={15}/></b></Link>
    </section>
    <section className="model-strip"><div><small>GNANI MODEL STACK</small><h3>Built around Indian speech</h3></div><div className="models"><span><b>Prisma</b><small>STT · v3.0</small></span><span><b>Evon</b><small>Reasoning · v3.3</small></span><span><b>Timbre</b><small>TTS · v3.0</small></span><span><b>Warp</b><small>Experimental · v2.0</small></span></div></section>
    <section className="status-panel"><div><small>INTEGRATION STATUS</small><h3>Provider readiness</h3><p>Live inference remains disabled until official Gnani API contracts and credentials are verified and implemented.</p></div><div className="provider-list">{config?.providers.map((item) => <div key={item.provider}><span>{item.provider} · {item.model}</span><strong className={item.configured ? "ready" : "pending"}>{item.configured ? "Configured" : "Pending"}</strong></div>) ?? <span>Backend not connected</span>}</div></section>
    <footer>VaaniShield · A simulated safety experience, not a real phone-call protection service.</footer>
  </main>;
}

function CallScreen({ assistant = false }: { assistant?: boolean }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"intro" | "incoming" | "active" | "ended">("intro");
  const [status, setStatus] = useState("Ready");
  const [seconds, setSeconds] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [threat, setThreat] = useState<ThreatPayload | null>(null);
  const [phrase, setPhrase] = useState("Hello sir, main bank se bol raha hoon. Account block hone se bachane ke liye apna OTP bata dijiye.");
  const [busy, setBusy] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream>();
  const contextRef = useRef<AudioContext>();
  const processorRef = useRef<ScriptProcessorNode>();
  const sourceRef = useRef<MediaStreamAudioSourceNode>();
  const seqRef = useRef(0);
  const duration = useMemo(() => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`, [seconds]);

  useEffect(() => {
    if (phase !== "active") return;
    const timer = window.setInterval(() => setSeconds((v) => v + 1), 1000);
    return () => window.clearInterval(timer);
  }, [phase]);

  useEffect(() => () => {
    socketRef.current?.close();
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    void contextRef.current?.close();
    stopMicrophone(streamRef.current);
  }, []);

  async function acceptCall() {
    setBusy(true);
    setStatus("Requesting microphone permission…");
    try {
      const stream = await requestRawMicrophone();
      streamRef.current = stream;
      const session = await createSession(assistant ? "assistant" : "scam_demo");
      const ws = new WebSocket(socketUrl(session.session_id));
      socketRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ event: "session.start", payload: { language: "hi-en" } }));
        setPhase("active");
        setStatus("Session connected · Gnani inference pending");
        setBusy(false);
        setTranscript(assistant ? "Mic connected. Live assistant responses require verified Gnani adapters." : "Demo session connected. Speak, or analyse the fictional sample below.");
        captureAudio(stream, ws);
      };
      ws.onmessage = (message) => {
        const event = JSON.parse(message.data) as { event: string; payload: Record<string, unknown> };
        if (event.event === "threat.detected") setThreat(event.payload as unknown as ThreatPayload);
        if (event.event === "transcript.partial" || event.event === "transcript.final") setTranscript(String(event.payload.text ?? ""));
        if (event.event === "provider.status") setStatus("Audio session active · provider not configured");
        if (event.event === "error") setStatus(String(event.payload.message ?? "Session error"));
      };
      ws.onerror = () => { setStatus("WebSocket connection error"); setBusy(false); };
      ws.onclose = () => setStatus("Session disconnected");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Unable to start session.");
      setBusy(false);
    }
  }

  function captureAudio(stream: MediaStream, ws: WebSocket) {
    const context = new AudioContext();
    contextRef.current = context;
    const source = context.createMediaStreamSource(stream);
    sourceRef.current = source;
    // Capture is transport scaffolding. Provider-specific resampling/framing is pending
    // verification of the exact official Gnani streaming contract.
    const processor = context.createScriptProcessor(2048, 1, 1);
    processorRef.current = processor;
    processor.onaudioprocess = (event) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      const data = encodePcm16(event.inputBuffer.getChannelData(0));
      ws.send(JSON.stringify({ event: "audio.chunk", payload: {
        sequence: seqRef.current++, encoding: "pcm_s16le", channels: 1,
        sample_rate: context.sampleRate, data
      }}));
    };
    source.connect(processor);
    const silentGain = context.createGain();
    silentGain.gain.value = 0;
    processor.connect(silentGain);
    silentGain.connect(context.destination);
  }

  function analyseSample() {
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setStatus("Accept the demo call first.");
      return;
    }
    socketRef.current.send(JSON.stringify({ event: "transcript.demo", payload: { text: phrase } }));
    setTranscript(phrase);
  }

  function endCall() {
    socketRef.current?.send(JSON.stringify({ event: "session.end", payload: {} }));
    socketRef.current?.close();
    socketRef.current = null;
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    void contextRef.current?.close();
    stopMicrophone(streamRef.current);
    streamRef.current = undefined;
    setPhase("ended");
    setStatus("Session ended");
  }

  return <main className="call-page">
    <button className="back-button" onClick={() => navigate("/")}><ArrowLeft size={16}/> Back to home</button>
    {phase === "intro" && <section className="call-intro"><div className="intro-orb">{assistant ? <AudioLines size={34}/> : <ShieldAlert size={34}/>}</div><small>{assistant ? "VOICE CONVERSATION" : "SIMULATED INCOMING CALL"}</small><h1>{assistant ? "Talk to Vaani." : "Test your protection."}</h1><p>{assistant ? "A separate Hinglish voice session. Actual model responses require the verified provider adapters." : "Play the caller in a simulated call. Speak in Hinglish and test the local demonstration rule engine."}</p><div className="permission-note"><Mic size={16}/> Microphone access is required for audio capture.</div><button className="button primary" onClick={() => setPhase("incoming")}>{assistant ? <Headphones size={17}/> : <PhoneCall size={17}/>} {assistant ? "Prepare voice session" : "Simulate incoming call"}</button></section>}
    {phase === "incoming" && <section className="phone-shell"><div className="phone-top"><span>VAANISHIELD DEMO</span><span>•••</span></div><div className="caller-avatar"><PhoneCall size={28}/></div><small>{assistant ? "VOICE ASSISTANT" : "INCOMING DEMO CALL"}</small><h2>{assistant ? "Vaani Assistant" : "Unknown Caller"}</h2><p>{assistant ? "Hinglish · AI voice session" : "Simulated caller · Not a real phone call"}</p><div className="incoming-actions"><button className="decline" onClick={() => setPhase("intro")}><PhoneOff/></button><button className="accept" disabled={busy} onClick={acceptCall}><Phone/></button></div><div className="action-labels"><span>Cancel</span><span>{busy ? "Connecting…" : "Accept"}</span></div><div className="status-text">{status}</div></section>}
    {phase === "active" && <section className={`phone-shell active-shell ${threat ? "alert-shell" : ""}`}><div className="phone-top"><span>{assistant ? "VAANI ASSISTANT" : "SCAMSHIELD"}</span><span className="live-dot"/></div><div className="active-caller"><div className="caller-avatar">{assistant ? <AudioLines size={28}/> : <Shield size={28}/>}</div><h2>{assistant ? "Vaani" : "Unknown Caller"}</h2><p>{duration} · {status}</p></div>
      {threat && !assistant ? <div className="threat-alert"><div><ShieldAlert size={18}/> SCAM CALL DETECTED</div><h3>Do not share your OTP.</h3><p>{threat.warning_message}</p><div className="threat-meta"><b>{threat.scam_type.replaceAll("_", " ")}</b><b>{threat.risk_level.toUpperCase()}</b></div>{threat.evidence.map((item) => <small key={item}>• {item}</small>)}</div> : <div className="wave-panel"><div className="wave-bars">{Array.from({ length: 29 }, (_, i) => <i key={i} style={{ height: `${12 + ((i * 17) % 43)}px` }}/>)}</div><span>{assistant ? "Listening · responses unavailable until Gnani is configured" : "Demo audio session active"}</span></div>}
      <div className="transcript"><small>TRANSCRIPT</small><p>{transcript || "Transcript will appear when Prisma integration is connected."}</p></div>
      {!assistant && <div className="demo-input"><label htmlFor="demo-phrase">FICTIONAL DEMO PHRASE · LOCAL RULE TEST</label><textarea id="demo-phrase" value={phrase} onChange={(e) => setPhrase(e.target.value)}/><button onClick={analyseSample}>Analyse sample phrase</button></div>}
      <div className="call-controls"><button title="Microphone capture"><Mic size={19}/></button><button title="Audio"><Volume2 size={19}/></button><button className="hangup" title="End session" onClick={endCall}><PhoneOff size={20}/></button></div><span className="status-text">{status}</span>
    </section>}
    {phase === "ended" && <section className="ended-card"><CheckCircle2 size={34}/><h2>Session ended</h2><p>{threat ? "A suspicious request was flagged in the demo rule test." : "Your simulated session has finished."}</p>{threat && <div className="threat-meta"><b>{threat.scam_type}</b><b>{threat.risk_level}</b></div>}<button className="button primary" onClick={() => { setPhase("intro"); setSeconds(0); setTranscript(""); setThreat(null); setStatus("Ready"); }}>Start again</button></section>}
  </main>;
}

export default function App() {
  return <><Header/><Routes><Route path="/" element={<Home/>}/><Route path="/scam-demo" element={<CallScreen/>}/><Route path="/assistant" element={<CallScreen assistant/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></>;
}
