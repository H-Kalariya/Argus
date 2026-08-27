import React, { useState, useEffect, useRef, useMemo } from 'react'
import './NetworkDashboard.css'

const API = 'http://localhost:8000'

const ACTION_META = {
  MONITORING: { cls: 'monitor', label: '✅ MONITORING' },
  APPROVE: { cls: 'monitor', label: '✅ APPROVE' },
  STEP_UP_CHALLENGE: { cls: 'stepup', label: '⚠️ STEP-UP' },
  FLAG_FOR_REVIEW: { cls: 'flag', label: '🔍 FLAG FOR REVIEW' },
  BLOCK: { cls: 'block', label: '⛔ BLOCK' },
}

// Deterministic layout: position each node once, reused across steps.
function useLayout(allEvents) {
  return useMemo(() => {
    const pos = {}
    const accounts = []
    const signals = []
    const seen = new Set()
    for (const e of allEvents) {
      for (const id of [e.node_id, e.edge_to]) {
        if (!id || seen.has(id)) continue
        seen.add(id)
        if (id.startsWith('acct:')) accounts.push(id)
        else signals.push(id)
      }
    }
    const W = 460, H = 460
    accounts.forEach((id, i) => {
      const a = (2 * Math.PI * i) / Math.max(accounts.length, 1) - Math.PI / 2
      pos[id] = { x: W / 2 + Math.cos(a) * 165, y: H / 2 + Math.sin(a) * 165 }
    })
    signals.forEach((id, i) => {
      const a = (2 * Math.PI * i) / Math.max(signals.length, 1)
      pos[id] = { x: W / 2 + Math.cos(a) * 70, y: H / 2 + Math.sin(a) * 70 }
    })
    return { pos, W, H }
  }, [allEvents])
}

function Graph({ layout, visibleEvents, latestId }) {
  const { pos, W, H } = layout
  const nodeSet = new Set()
  const edges = []
  visibleEvents.forEach((e) => {
    nodeSet.add(e.node_id)
    if (e.edge_to) {
      nodeSet.add(e.edge_to)
      edges.push({ from: e.node_id, to: e.edge_to, type: e.edge_type, fraud: e.is_fraud, sub: e.edge_subtype })
    }
  })
  const nodes = [...nodeSet]
  const labelFor = (id) => {
    const e = [...visibleEvents].reverse().find((x) => x.node_id === id || x.edge_to === id)
    if (id.startsWith('acct:')) {
      const ev = visibleEvents.find((x) => x.node_id === id)
      return ev ? ev.label : id.replace('acct:', '')
    }
    return e ? (e.edge_subtype ? id.split(':').pop() : id) : id.split(':').pop()
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="cc-graph">
      {edges.map((ed, i) => {
        const a = pos[ed.from], b = pos[ed.to]
        if (!a || !b) return null
        return (
          <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            className={`edge ${ed.type} ${ed.fraud ? 'fraud' : ''}`} />
        )
      })}
      {nodes.map((id) => {
        const p = pos[id]
        if (!p) return null
        const acct = id.startsWith('acct:')
        const ev = visibleEvents.find((x) => x.node_id === id || x.edge_to === id)
        const fraud = ev && ev.is_fraud
        const isNew = latestId && (id === latestId)
        return (
          <g key={id} className={isNew ? 'node-appear' : ''}>
            <circle cx={p.x} cy={p.y} r={acct ? 12 : 7}
              className={`node ${acct ? 'acct' : 'sig'} ${fraud ? 'fraud' : ''}`} />
            <text x={p.x} y={p.y - (acct ? 16 : 12)} className="node-label">{labelFor(id)}</text>
          </g>
        )
      })}
    </svg>
  )
}

function TierRow({ icon, name, window, tier }) {
  const pct = Math.min((tier.count / tier.threshold) * 100, 100)
  return (
    <div className={`cc-tier ${tier.triggered ? 'triggered' : ''}`}>
      <span className="cc-tier-icon">{icon}</span>
      <div className="cc-tier-body">
        <div className="cc-tier-top">
          <span>{name} <em>· {window}</em></span>
          <span className="cc-tier-count">{tier.count}/{tier.threshold}</span>
        </div>
        <div className="cc-tier-bar"><div className="cc-tier-fill" style={{ width: `${pct}%` }} /></div>
      </div>
    </div>
  )
}

export default function NetworkDashboard() {
  const [scenarios, setScenarios] = useState([])
  const [active, setActive] = useState(null)   // scenario id
  const [replay, setReplay] = useState(null)   // replay payload
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    fetch(`${API}/graph/timeline/scenarios`)
      .then((r) => r.json())
      .then((d) => setScenarios(d.scenarios || []))
      .catch(console.error)
  }, [])

  const selectScenario = async (id) => {
    setActive(id)
    setStep(0)
    setPlaying(false)
    const data = await fetch(`${API}/graph/scenario/${id}/replay`).then((r) => r.json())
    setReplay(data)
    setPlaying(true)
  }

  const reset = () => {
    setActive(null); setReplay(null); setStep(0); setPlaying(false)
  }

  // autoplay
  useEffect(() => {
    clearInterval(timerRef.current)
    if (playing && replay) {
      timerRef.current = setInterval(() => {
        setStep((s) => {
          if (s >= replay.steps.length - 1) { setPlaying(false); return s }
          return s + 1
        })
      }, 1400)
    }
    return () => clearInterval(timerRef.current)
  }, [playing, replay])

  const allEvents = replay ? replay.events : []
  const layout = useLayout(allEvents)
  const visibleEvents = replay ? replay.events.slice(0, step + 1) : []
  const current = replay ? replay.steps[step] : null
  const decision = current ? current.decision.action : 'MONITORING'
  const meta = ACTION_META[decision] || ACTION_META.MONITORING
  const risk = current ? current.risk_score : 0
  const latestId = visibleEvents.length ? visibleEvents[visibleEvents.length - 1].node_id : null

  return (
    <div className="command-center">
      <div className="cc-scenario-bar">
        <button className="cc-reset" onClick={reset}>🔄 Reset</button>
        {scenarios.map((s) => (
          <button key={s.id} className={`cc-scn ${active === s.id ? 'active' : ''}`}
            onClick={() => selectScenario(s.id)}>
            {s.icon} {s.name}
          </button>
        ))}
      </div>

      {!replay && (
        <div className="cc-empty">Select a scenario above to replay the attack event-by-event.</div>
      )}

      {replay && (
        <>
          <div className="cc-grid">
            {/* LEFT: live database */}
            <div className="cc-panel">
              <h3>📊 Live Database (SQLite)</h3>
              <div className="cc-db">
                <table>
                  <thead>
                    <tr><th>Time</th><th>Node</th><th>Action</th><th>Link</th></tr>
                  </thead>
                  <tbody>
                    {visibleEvents.map((e, i) => (
                      <tr key={i} className={`${i === visibleEvents.length - 1 ? 'new-row' : ''} ${e.is_fraud ? 'fraud' : ''}`}>
                        <td className="mono">{e.timestamp}</td>
                        <td className="mono">{e.node_id.split(':').slice(-1)[0].slice(0, 12)}</td>
                        <td>{e.action}</td>
                        <td>{e.edge_type || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="cc-event-desc">{current && current.event.description}</p>
            </div>

            {/* CENTER: graph */}
            <div className="cc-panel">
              <h3>🕸️ Identity Graph</h3>
              <Graph layout={layout} visibleEvents={visibleEvents} latestId={latestId} />
              <div className="cc-legend">
                <span><i className="dot acct" /> account</span>
                <span><i className="dot sig" /> signal</span>
                <span><i className="ln hard" /> hard link</span>
                <span><i className="ln soft" /> soft link</span>
              </div>
            </div>

            {/* RIGHT: decision engine */}
            <div className="cc-panel">
              <h3>⚡ Decision Engine</h3>
              <div className="cc-risk">
                <div className="cc-risk-score">{risk.toFixed(1)}</div>
                <div className="cc-risk-label">Risk Score</div>
                <div className="cc-risk-bar">
                  <div className="cc-risk-fill" style={{ width: `${Math.min(risk * 12, 100)}%` }} />
                </div>
              </div>

              <div className="cc-tiers">
                {current && <>
                  <TierRow icon="⚡" name="Tier 1" window="15 min" tier={current.tiers.tier1} />
                  <TierRow icon="🕐" name="Tier 2" window="24 h" tier={current.tiers.tier2} />
                  <TierRow icon="📅" name="Tier 3" window="7 days" tier={current.tiers.tier3} />
                </>}
              </div>

              <div className={`cc-decision ${meta.cls}`}>
                <div className="cc-decision-label">Action</div>
                <div className="cc-decision-value">{meta.label}</div>
                <div className="cc-decision-reason">{current && current.decision.reason}</div>
              </div>
            </div>
          </div>

          {/* Timeline scrubber */}
          <div className="cc-timeline">
            <button onClick={() => setStep((s) => Math.max(0, s - 1))} disabled={step === 0}>◀</button>
            <button onClick={() => setPlaying((p) => !p)}>{playing ? '⏸' : '▶'}</button>
            <button onClick={() => setStep((s) => Math.min(replay.steps.length - 1, s + 1))}
              disabled={step >= replay.steps.length - 1}>▶▶</button>
            <div className="cc-track">
              {replay.steps.map((st, i) => (
                <div key={i}
                  className={`cc-dot ${i <= step ? 'done' : ''} ${i === step ? 'current' : ''} ${st.event.is_fraud ? 'fraud' : ''}`}
                  onClick={() => { setPlaying(false); setStep(i) }}>
                  <span className="cc-tip">{st.event.timestamp}: {st.event.description}</span>
                </div>
              ))}
            </div>
            <span className="cc-step-count">{step + 1}/{replay.steps.length}</span>
          </div>
        </>
      )}
    </div>
  )
}
