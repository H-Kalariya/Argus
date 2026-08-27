import React, { useState, useRef, useEffect } from 'react'
import './App.css'
import NetworkDashboard from './NetworkDashboard'

const API = 'http://localhost:8000'

function App() {
  const [tab, setTab] = useState('kyc') // 'kyc' | 'network'

  // Enrollment (ground truth)
  const [refImage, setRefImage] = useState(null)      // { blob, url }
  const [refAudio, setRefAudio] = useState(null)      // { blob, url }
  const [enrollAudioRecording, setEnrollAudioRecording] = useState(false)

  // Challenge
  const [challenge, setChallenge] = useState(null)
  const [isRecording, setIsRecording] = useState(false)
  const [videoUrl, setVideoUrl] = useState(null)
  const [countdown, setCountdown] = useState(null)
  const [isVerifying, setIsVerifying] = useState(false)
  const [kycResult, setKycResult] = useState(null)

  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const audioRecorderRef = useRef(null)
  const audioChunksRef = useRef([])

  // Pick a container/codec that both the browser and Gemini support.
  const pickMime = (candidates) => {
    for (const m of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) return m
    }
    return ''
  }
  const videoMimeRef = useRef('')
  const audioMimeRef = useRef('')
  useEffect(() => {
    videoMimeRef.current = pickMime([
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
      'video/mp4',
    ])
    audioMimeRef.current = pickMime([
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
    ])
  }, [])

  useEffect(() => {
    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
      } catch (err) {
        console.error('Error accessing camera:', err)
      }
    }
    setupCamera()
    return () => {
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop())
    }
  }, [])

  // ---- Enrollment: capture reference face photo from current video frame ----
  const captureReferenceFace = () => {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      if (refImage?.url) URL.revokeObjectURL(refImage.url)
      setRefImage({ blob, url: URL.createObjectURL(blob) })
    }, 'image/jpeg', 0.92)
  }

  // ---- Enrollment: record a short reference voice sample ----
  const startEnrollAudio = () => {
    const stream = streamRef.current
    if (!stream) return
    audioChunksRef.current = []
    const audioStream = new MediaStream(stream.getAudioTracks())
    const mime = audioMimeRef.current
    const recorder = mime ? new MediaRecorder(audioStream, { mimeType: mime }) : new MediaRecorder(audioStream)
    audioRecorderRef.current = recorder
    recorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data) }
    recorder.onstop = () => {
      const blob = new Blob(audioChunksRef.current, { type: (mime || 'audio/webm').split(';')[0] })
      if (refAudio?.url) URL.revokeObjectURL(refAudio.url)
      setRefAudio({ blob, url: URL.createObjectURL(blob) })
    }
    recorder.start()
    setEnrollAudioRecording(true)
    setTimeout(() => stopEnrollAudio(), 5000) // 5s sample
  }

  const stopEnrollAudio = () => {
    if (audioRecorderRef.current && audioRecorderRef.current.state !== 'inactive') {
      audioRecorderRef.current.stop()
      setEnrollAudioRecording(false)
    }
  }

  const enrolled = refImage && refAudio

  // ---- Challenge ----
  const fetchChallenge = async () => {
    try {
      const res = await fetch(`${API}/challenge`)
      const data = await res.json()
      setChallenge(data)
      setVideoUrl(null)
      setKycResult(null)
    } catch (err) {
      console.error('Error fetching challenge:', err)
    }
  }

  const startRecording = () => {
    setVideoUrl(null)
    setKycResult(null)
    chunksRef.current = []
    const stream = streamRef.current
    if (!stream) return

    const mime = videoMimeRef.current
    const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream)
    mediaRecorderRef.current = recorder
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: (mime || 'video/webm').split(';')[0] })
      setVideoUrl(URL.createObjectURL(blob))
      await submitKyc(blob)
    }
    recorder.start()
    setIsRecording(true)
    setCountdown(7)
  }

  const submitKyc = async (videoBlob) => {
    if (!challenge || !enrolled) return
    setIsVerifying(true)
    const form = new FormData()
    form.append('instruction', challenge.action)
    form.append('spoken_phrase', challenge.spoken_phrase)
    form.append('reference_image', refImage.blob, 'reference.jpg')
    form.append('reference_audio', refAudio.blob, 'reference.webm')
    form.append('video', videoBlob, 'challenge.webm')
    try {
      const res = await fetch(`${API}/verify/kyc`, { method: 'POST', body: form })
      const result = await res.json()
      console.log('KYC Result:', result)
      setKycResult(result)
    } catch (err) {
      console.error('KYC error:', err)
      setKycResult({ error: err.message })
    } finally {
      setIsVerifying(false)
    }
  }

  useEffect(() => {
    let timer
    if (isRecording && countdown > 0) {
      timer = setTimeout(() => setCountdown(countdown - 1), 1000)
    } else if (isRecording && countdown === 0) {
      stopRecording()
    }
    return () => clearTimeout(timer)
  }, [isRecording, countdown])

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      setCountdown(null)
    }
  }

  const Check = ({ ok, label }) => (
    <li className={ok ? 'check pass' : 'check fail'}>
      <span>{ok ? '✅' : '❌'}</span> {label}
    </li>
  )

  return (
    <div className="App">
      <h1>Project Medusa</h1>

      <nav className="tab-nav">
        <button className={`tab-btn ${tab === 'kyc' ? 'active' : ''}`} onClick={() => setTab('kyc')}>
          🔐 KYC Scanner
        </button>
        <button className={`tab-btn ${tab === 'network' ? 'active' : ''}`} onClick={() => setTab('network')}>
          🕸️ Fraud Network
        </button>
      </nav>

      {tab === 'network' && <NetworkDashboard />}

      {tab === 'kyc' && (
        <>
          <div className="video-container">
            <video ref={videoRef} autoPlay muted playsInline className="live-video" />
          </div>

          {/* STEP 1: Enrollment */}
          <section className="step">
            <h2>Step 1 — Enroll (Ground Truth)</h2>
            <p className="hint">Capture your face and record your voice. These are used as the reference to match against.</p>
            <div className="enroll-grid">
              <div className="enroll-card">
                <h3>Reference Face</h3>
                {refImage ? (
                  <img src={refImage.url} alt="reference face" className="ref-thumb" />
                ) : (
                  <div className="ref-placeholder">No photo yet</div>
                )}
                <button onClick={captureReferenceFace} className="primary-btn">
                  {refImage ? 'Retake Photo' : 'Capture Face'}
                </button>
              </div>

              <div className="enroll-card">
                <h3>Reference Voice</h3>
                {refAudio ? (
                  <audio src={refAudio.url} controls className="ref-audio" />
                ) : (
                  <div className="ref-placeholder">No voice sample yet</div>
                )}
                {enrollAudioRecording ? (
                  <div className="recording-indicator"><span className="dot pulse" /> Recording 5s...</div>
                ) : (
                  <button onClick={startEnrollAudio} className="primary-btn">
                    {refAudio ? 'Re-record Voice' : 'Record Voice (say anything for 5s)'}
                  </button>
                )}
              </div>
            </div>
          </section>

          {/* STEP 2: Challenge */}
          <section className="step">
            <h2>Step 2 — Payment Challenge</h2>
            {!enrolled && <p className="warn">Complete enrollment above first.</p>}
            <button onClick={fetchChallenge} className="primary-btn" disabled={!enrolled}>
              Get New Challenge
            </button>

            {challenge && (
              <div className="challenge-box">
                <p className="instruction">{challenge.action}</p>
                <p className="phrase">🗣️ Say: <strong>"{challenge.spoken_phrase}"</strong></p>
              </div>
            )}

            {challenge && (
              <div className="recording-controls">
                {!isRecording ? (
                  <button onClick={startRecording} className="record-btn" disabled={!enrolled}>
                    Start Recording
                  </button>
                ) : (
                  <div className="recording-indicator">
                    <span className="dot pulse" /> Recording... {countdown}s
                    <button onClick={stopRecording} className="stop-btn ml-2">Stop Early</button>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* STEP 3: Result */}
          {(videoUrl || isVerifying || kycResult) && (
            <section className="step">
              <h2>Step 3 — Verification Result</h2>
              {videoUrl && <video src={videoUrl} controls className="preview-video" />}

              {isVerifying && (
                <div className="verifying-box">
                  <span className="dot pulse" /> Verifying face, voice & liveness... this takes a few seconds.
                </div>
              )}

              {kycResult && !kycResult.error && (
                <div className={`result-box ${kycResult.overall_kyc_pass ? 'pass' : 'fail'}`}>
                  <h3>{kycResult.overall_kyc_pass ? '✅ Payment Authorized' : '❌ Verification Failed'}</h3>
                  <ul className="checklist">
                    <Check ok={kycResult.face_match} label={`Face match (${Math.round((kycResult.face_confidence || 0) * 100)}%)`} />
                    <Check ok={kycResult.voice_match} label={`Voice match (${Math.round((kycResult.voice_confidence || 0) * 100)}%)`} />
                    <Check ok={kycResult.action_performed} label="Action performed" />
                    <Check ok={kycResult.spoken_phrase_correct} label="Correct phrase spoken" />
                    <Check ok={kycResult.liveness_pass} label="Liveness confirmed" />
                  </ul>
                  <p className="transcript"><strong>Heard:</strong> "{kycResult.spoken_text}"</p>
                  <p className="reasoning">{kycResult.reasoning}</p>
                </div>
              )}

              {kycResult && kycResult.error && (
                <div className="result-box error">
                  <h3>❌ Error</h3>
                  <pre>{kycResult.error}</pre>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  )
}

export default App
