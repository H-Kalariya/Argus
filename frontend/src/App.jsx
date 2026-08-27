import React, { useState, useRef, useEffect } from 'react'
import './App.css'

function App() {
  const [challenge, setChallenge] = useState(null)
  const [isRecording, setIsRecording] = useState(false)
  const [videoUrl, setVideoUrl] = useState(null)
  const [countdown, setCountdown] = useState(null)
  const [semanticResult, setSemanticResult] = useState(null)
  
  const videoRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  useEffect(() => {
    // Start camera
    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (err) {
        console.error("Error accessing camera:", err)
      }
    }
    setupCamera()
  }, [])

  const fetchChallenge = async () => {
    try {
      const response = await fetch('http://localhost:8000/challenge')
      const data = await response.json()
      setChallenge(data)
      setVideoUrl(null)
      setSemanticResult(null)
    } catch (err) {
      console.error("Error fetching challenge:", err)
    }
  }

  const startRecording = () => {
    setVideoUrl(null)
    setSemanticResult(null)
    chunksRef.current = []
    const stream = videoRef.current.srcObject
    if (!stream) return

    mediaRecorderRef.current = new MediaRecorder(stream)
    mediaRecorderRef.current.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    mediaRecorderRef.current.onstop = async () => {
      const blob = new Blob(chunksRef.current, { type: 'video/webm' })
      const url = URL.createObjectURL(blob)
      setVideoUrl(url)
      
      // Upload to backend
      if (challenge) {
        const formData = new FormData()
        formData.append('instruction', challenge.instruction)
        formData.append('video', blob, 'challenge.webm')
        
        try {
          const response = await fetch('http://localhost:8000/verify/semantic', {
            method: 'POST',
            body: formData
          })
          const result = await response.json()
          console.log("Semantic Verification Result:", result)
          setSemanticResult(result)
        } catch (err) {
          console.error("Upload error:", err)
        }
      }
    }
    mediaRecorderRef.current.start()
    setIsRecording(true)
    
    // Auto stop after 7 seconds for a challenge
    setCountdown(7)
  }

  useEffect(() => {
    let timer;
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

  return (
    <div className="App">
      <h1>Project Medusa: Challenge Interface</h1>
      
      <div className="challenge-container">
        <button onClick={fetchChallenge} className="primary-btn">
          Get New Challenge
        </button>
        {challenge && (
          <div className="challenge-box">
            <h2>Challenge Instructions:</h2>
            <p className="instruction">{challenge.instruction}</p>
          </div>
        )}
      </div>

      <div className="video-container">
        <video 
          ref={videoRef} 
          autoPlay 
          muted 
          playsInline 
          className="live-video"
        />
        
        {challenge && (
          <div className="recording-controls">
            {!isRecording ? (
              <button onClick={startRecording} className="record-btn">
                Start Recording
              </button>
            ) : (
              <div className="recording-indicator">
                <span className="dot pulse"></span> 
                Recording... {countdown}s
                <button onClick={stopRecording} className="stop-btn ml-2">Stop Early</button>
              </div>
            )}
          </div>
        )}
      </div>

      {videoUrl && (
        <div className="preview-container">
          <h2>Recorded Preview</h2>
          <video src={videoUrl} controls className="preview-video" />
          
          {semanticResult && (
            <div className="result-box">
              <h3>Semantic Verification Result:</h3>
              <pre>{JSON.stringify(semanticResult, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default App
