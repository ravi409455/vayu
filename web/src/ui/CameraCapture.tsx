import { Camera, RefreshCw, Square, Video as VideoIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Modal } from "./kit";

export const MAX_VIDEO_SECONDS = 60;

/** A live camera right in the page (works on a laptop webcam and on a phone). Photo: shutter,
 *  then keep or retake. Video: record up to a minute, then keep or retake. If the camera cannot be
 *  opened it says why and offers the device's own camera app instead. */
export function CameraCapture({ kind, label, onDone, onClose, onFallback }: {
  kind: "photo" | "video"; label: string; onDone: (file: File) => void; onClose: () => void; onFallback: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | undefined>(undefined);
  const [error, setError] = useState("");
  const [shot, setShot] = useState<{ blob: Blob; url: string } | null>(null);
  const [recording, setRecording] = useState(false);
  const [live, setLive] = useState(false);       // the shutter waits until the camera is really showing a picture
  const [seconds, setSeconds] = useState(0);

  async function open() {
    setError("");
    if (!navigator.mediaDevices?.getUserMedia) return setError("This browser cannot open the camera here.");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: kind === "video" });
      if (video.current) { video.current.srcObject = stream.current; await video.current.play().catch(() => {}); }
    } catch (e) {
      const name = (e as DOMException).name;
      setError(name === "NotAllowedError" ? "Camera permission was refused. Allow it in the browser's address bar and try again." : name === "NotFoundError" ? "No camera was found on this device." : "The camera could not be opened.");
    }
  }
  // after "Retake" the live <video> is a new element: give it the running camera again
  useEffect(() => {
    if (!shot && video.current && stream.current && video.current.srcObject !== stream.current) {
      video.current.srcObject = stream.current;
      void video.current.play().catch(() => {});
    }
  }, [shot]);
  const stop = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; window.clearInterval(timer.current); };
  useEffect(() => { void open(); return stop; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    c.toBlob((b) => b && setShot({ blob: b, url: URL.createObjectURL(b) }), "image/jpeg", 0.9);
  }
  function record() {
    if (!stream.current) return;
    chunks.current = [];
    const r = new MediaRecorder(stream.current);
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = () => { const blob = new Blob(chunks.current, { type: r.mimeType || "video/webm" }); setShot({ blob, url: URL.createObjectURL(blob) }); };
    r.start();
    recorder.current = r;
    setRecording(true); setSeconds(0);
    timer.current = window.setInterval(() => setSeconds((s) => { if (s + 1 >= MAX_VIDEO_SECONDS) finish(); return s + 1; }), 1000);
  }
  function finish() { window.clearInterval(timer.current); recorder.current?.state === "recording" && recorder.current.stop(); setRecording(false); }
  function keep() {
    if (!shot) return;
    const ext = kind === "photo" ? "jpg" : shot.blob.type.includes("mp4") ? "mp4" : "webm";
    onDone(new File([shot.blob], `${kind}-${Date.now()}.${ext}`, { type: shot.blob.type }));
    stop();
  }
  const retake = () => { if (shot) URL.revokeObjectURL(shot.url); setLive(false); setShot(null); };

  return (
    <Modal title={label} onClose={() => { stop(); onClose(); }} actions={<button onClick={() => { stop(); onClose(); }}>Cancel</button>}>
      {error ? (
        <div role="alert">
          <p className="error">{error}</p>
          <div className="bar"><button onClick={() => void open()}><RefreshCw size={14} aria-hidden /> Try again</button><button onClick={() => { stop(); onFallback(); }}>Use the device's camera app</button></div>
        </div>
      ) : (
        <>
          <div className="camera-box">
            {shot ? (kind === "photo" ? <img src={shot.url} alt="Preview of what you captured" /> : <video src={shot.url} controls playsInline />) : <video ref={video} muted playsInline aria-label="Live camera" onLoadedData={() => setLive(true)} />}
            {recording && <span className="rec">● {seconds}s / {MAX_VIDEO_SECONDS}s</span>}
          </div>
          <div className="bar" style={{ justifyContent: "center", marginTop: 12 }}>
            {shot ? (
              <><button onClick={retake}><RefreshCw size={14} aria-hidden /> Retake</button><button className="primary" onClick={keep}>Use this {kind}</button></>
            ) : kind === "photo" ? (
              <button className="primary shutter" onClick={snap} disabled={!live} aria-label="Take photo"><Camera size={20} aria-hidden /> Take photo</button>
            ) : recording ? (
              <button className="danger" onClick={finish} aria-label="Stop recording"><Square size={16} aria-hidden /> Stop</button>
            ) : (
              <button className="primary" onClick={record} aria-label="Start recording"><VideoIcon size={18} aria-hidden /> Record</button>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
