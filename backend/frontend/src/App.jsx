import { useEffect, useMemo, useState } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

const OVERVIEW_POLL_MS = 2000
const PERF_POLL_MS = 5000
const HISTORY_POLL_MS = 5000
const HISTORY_OPTIONS = [30, 60, 120]

const getNodeKey = (node) => `${node.gateway_id}:${node.node_id}`
const pad2 = (n) => String(n).padStart(2, '0')
const fmt = (v, d = 1) => (v == null || !Number.isFinite(Number(v)) ? '--' : Number(v).toLocaleString('vi-VN', { maximumFractionDigits: d, minimumFractionDigits: d }))

function displayTime(timestamp) {
  if (!timestamp) return '--:--:--'
  const t = new Date(timestamp)
  return Number.isNaN(t.getTime()) ? '--:--:--' : t.toLocaleTimeString('vi-VN', { hour12: false })
}

function displayAge(ageS) {
  if (ageS == null) return 'chưa có dữ liệu'
  if (ageS < 0) return 'vừa xong'
  if (ageS < 60) return `${Math.floor(ageS)} giây trước`
  if (ageS < 3600) return `${Math.floor(ageS / 60)} phút trước`
  return `${Math.floor(ageS / 3600)} giờ trước`
}

const ROLE_LABEL = { host: 'HOST', source: 'SOURCE', relay: 'RELAY' }

function useJson(url, intervalMs, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!url) { setData(null); return undefined }
    let active = true
    let busy = false
    async function load() {
      if (busy) return
      busy = true
      try {
        const r = await fetch(url)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const j = await r.json()
        if (active) { setData(j); setError('') }
      } catch (e) {
        if (active) setError(e.message)
      } finally {
        busy = false
      }
    }
    load()
    const t = setInterval(load, intervalMs)
    return () => { active = false; clearInterval(t) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, intervalMs, ...deps])
  return [data, error]
}

function GatewayBar({ gateways }) {
  if (!gateways?.length) return <span className="system-tag system-wait"><span className="live-dot" />Chưa có Gateway</span>
  return gateways.map(g => {
    const st = g.status || {}
    const online = st.online !== false && g.status_age_s != null && g.status_age_s < 60
    const bad = st.uart_bad_pct_5min
    return (
      <span key={g.gateway_id} className={`system-tag ${online ? '' : 'system-wait'}`} title="Trạng thái Raspberry Pi gửi qua MQTT mỗi 15 giây">
        <span className="live-dot" />
        {g.gateway_id}: {online ? 'online' : 'offline'}
        {bad != null && <> · UART lỗi {fmt(bad, 1)}%</>}
        {st.backlog != null && <> · tồn {st.backlog}</>}
      </span>
    )
  })
}

function NodeCard({ node, selected, onSelect }) {
  const r = node.latest || {}
  const w = node.last_5min || {}
  const light = r.light_raw != null && r.light_raw !== 65535 ? r.light_raw : null
  const pressure = r.pressure_pa != null && r.pressure_pa > 0 ? r.pressure_pa / 100 : null
  const noSensor = node.role === 'host' && [r.temperature_c, r.humidity_percent, light, pressure].every(v => v == null)
  return (
    <button type="button" className={`lwb-node ${selected ? 'selected' : ''} ${node.online ? 'online' : 'offline'}`} onClick={onSelect}>
      <div className="lwb-node-head">
        <strong>Node {pad2(node.node_id)}</strong>
        <span className={`role-badge role-${node.role}`}>{ROLE_LABEL[node.role] || node.role}</span>
        <span className={`node-state ${node.online ? 'online' : 'offline'}`}><span />{node.online ? 'Live' : 'Offline'}</span>
      </div>
      {noSensor ? (
        <div className="lwb-node-note">Điều phối mạng (không đo cảm biến)</div>
      ) : (
        <div className="lwb-node-values">
          <div><small>Nhiệt độ</small><b>{fmt(r.temperature_c)}<i>°C</i></b></div>
          <div><small>Độ ẩm</small><b>{fmt(r.humidity_percent)}<i>%</i></b></div>
          <div><small>Ánh sáng</small><b>{fmt(light, 0)}<i>raw</i></b></div>
          <div><small>Áp suất</small><b>{fmt(pressure)}<i>hPa</i></b></div>
        </div>
      )}
      <div className="lwb-node-run">Run #{r.run ?? '--'}</div>
      <div className="lwb-node-foot">
        <span>seq #{r.seq ?? '--'}</span>
        {node.role !== 'host' && <span>delay {fmt(r.delay_ms, 0)} ms</span>}
        {node.role !== 'host' && <span>hop {r.hop_est ?? '--'}</span>}
        <span>{w.packets ?? 0} gói/5 phút</span>
        <span>{displayAge(node.age_s)}</span>
      </div>
    </button>
  )
}

const isNum = (v) => v != null && Number.isFinite(Number(v))

// Domain có đệm ±10% biên độ (tối thiểu minPad). 5 tick đều nhau; chọn số chữ số thập phân
// nhỏ nhất để mọi nhãn trục khác nhau (không lặp số).
function axisScale(data, key, minPad, clamp) {
  const vals = data.map(d => d[key]).filter(isNum).map(Number)
  if (!vals.length) return null
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  const pad = Math.max((hi - lo) * 0.1, minPad)
  let a = lo - pad
  let b = hi + pad
  if (clamp) { a = Math.max(clamp[0], a); b = Math.min(clamp[1], b) }
  const ticks = [0, 1, 2, 3, 4].map(i => a + ((b - a) * i) / 4)
  let decimals = 0
  while (decimals < 4 && new Set(ticks.map(t => t.toFixed(decimals))).size < ticks.length) decimals += 1
  return { domain: [a, b], ticks, decimals }
}

function MiniChart({ title, emptyLabel, data, series }) {
  const scales = {}
  series.forEach(s => {
    if (!data.some(d => isNum(d[s.key]))) return
    scales[s.axis] = scales[s.axis] || axisScale(data, s.key, s.minPad, s.clamp)
  })
  const active = series.filter(s => data.some(d => isNum(d[s.key])))
  const tick = { fontSize: 11, fill: '#8090a8' }
  return (
    <div className="chart-card">
      <div className="chart-card-title">{title}</div>
      {active.length ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 10, right: 6, left: 6, bottom: 4 }}>
            <CartesianGrid strokeDasharray="4 5" stroke="#e8edf5" vertical={false} />
            <XAxis dataKey="time" interval="preserveStartEnd" minTickGap={27} tickLine={false} axisLine={false} tick={tick} />
            {['t', 'h'].filter(ax => scales[ax]).map(ax => (
              <YAxis key={ax} yAxisId={ax} orientation={ax === 'h' ? 'right' : 'left'} domain={scales[ax].domain} ticks={scales[ax].ticks} type="number"
                tickFormatter={v => Number(v).toFixed(scales[ax].decimals)} allowDataOverflow
                tickLine={false} axisLine={false} width={46} tick={tick} />
            ))}
            <Tooltip formatter={v => (isNum(v) ? Number(v).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : v)} />
            {active.length > 1 && <Legend verticalAlign="bottom" height={26} iconType="circle" iconSize={9} />}
            {active.map(s => (
              <Line key={s.key} yAxisId={s.axis} type="linear" dataKey={s.key} name={s.name} stroke={s.color}
                strokeWidth={2.2} dot={false} connectNulls={false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : <div className="chart-empty">Node này chưa có cảm biến {emptyLabel}</div>}
    </div>
  )
}

function PerfTable({ perf, onRun }) {
  if (!perf || perf.run == null) {
    return <p className="perf-empty">Chưa có bản tin PERF_SUMMARY. HOST in thống kê mỗi 30 giây sau khi các SOURCE bắt đầu phát.</p>
  }
  const host = perf.config?.find(c => c.role === 'HOST' || c.role === 'host')
  return (
    <>
      <div className="perf-meta">
        <label>Run
          <select value={perf.run} onChange={e => onRun(e.target.value)}>
            {perf.runs.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
        {host && <span>Kênh {host.channel} · {host.tx_drive_dbm} dBm · N_TX {host.n_data_tx} · IPI {host.ipi_s}s · {host.expected} gói/source · payload {host.payload_bytes} B</span>}
        {perf.join_failed_nodes?.length > 0 && <span className="perf-warn">Join thất bại: node {perf.join_failed_nodes.join(', ')}</span>}
      </div>
      <div className="perf-table-wrap">
        <table className="perf-table">
          <thead>
            <tr>
              <th>Source</th><th>Nhận / Dự kiến</th><th>Tiến độ</th><th>Application yield</th><th>Flood delivery</th>
              <th>Delay min / avg / max (ms)</th><th>Relay cnt</th><th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {perf.sources.map(s => (
              <tr key={s.source}>
                <td>Node {pad2(s.source)}</td>
                <td>{s.received ?? '--'} / {s.expected ?? '--'}</td>
                <td><div className="mini-bar"><div style={{ width: `${Math.min(100, s.progress_pct || 0)}%` }} /></div>{fmt(s.progress_pct, 1)}%</td>
                <td>{s.application_yield_pct == null ? '--' : `${fmt(s.application_yield_pct, 2)}%`}</td>
                <td>{s.flood_delivery_pct == null ? '--' : `${fmt(s.flood_delivery_pct, 2)}%`}</td>
                <td>{fmt(s.delay_min_ms, 0)} / {fmt(s.delay_avg_ms, 0)} / {fmt(s.delay_max_ms, 0)}</td>
                <td>{s.relay_min == null ? '--' : `${s.relay_min}–${s.relay_max}`}</td>
                <td>{s.final ? <span className="tag-final">Đã chốt</span> : <span className="tag-running">Đang đo</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="perf-note">Application yield và flood delivery chỉ có sau khi SOURCE gửi REPORT (cuối lượt). Relay cnt &gt; 0 cho thấy gói đi qua bước lặp/chuyển tiếp của Glossy, không tự chứng minh multi-hop.</p>
    </>
  )
}

function App() {
  const [showOffline, setShowOffline] = useState(false)
  const [selectedKey, setSelectedKey] = useState(null)
  const [historyLimit, setHistoryLimit] = useState(60)
  const [run, setRun] = useState('')
  const [clock, setClock] = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setClock(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const [overview, overviewError] = useJson('/api/overview/', OVERVIEW_POLL_MS)
  const [perf] = useJson(`/api/perf/${run ? `?run=${run}` : ''}`, PERF_POLL_MS)

  const allNodes = useMemo(() => overview?.nodes || [], [overview])
  const nodes = showOffline ? allNodes : allNodes.filter(n => n.online)
  const onlineCount = allNodes.filter(n => n.online).length

  useEffect(() => {
    if (!nodes.length) return
    if (!selectedKey || !nodes.some(n => getNodeKey(n) === selectedKey)) setSelectedKey(getNodeKey(nodes[0]))
  }, [nodes, selectedKey])

  const selected = allNodes.find(n => getNodeKey(n) === selectedKey)
  const [gw, nodeId] = selectedKey ? selectedKey.split(':') : [null, null]
  const [historyRaw] = useJson(
    selectedKey ? `/api/nodes/${nodeId}/history/?gateway=${encodeURIComponent(gw)}&limit=${historyLimit}` : null,
    HISTORY_POLL_MS,
  )
  const history = useMemo(() => {
    if (!Array.isArray(historyRaw)) return []
    const latestRun = historyRaw[0]?.run ?? null
    return historyRaw
      .filter(r => latestRun == null || r.run === latestRun)
      .reverse()
      .map(r => ({
        ...r,
        time: displayTime(r.recv_ts_utc),
        light_raw: r.light_raw != null && r.light_raw !== 65535 ? r.light_raw : null,
        pressure_hpa: r.pressure_pa != null && r.pressure_pa > 0 ? r.pressure_pa / 100 : null,
      }))
  }, [historyRaw])

  return (
    <div className="app-shell">
      <div className="dashboard">
        <header className="topbar">
          <div className="brand-group">
            <div>
              <div className="brand-kicker">LWB / GLOSSY · CC2538 · RASPBERRY PI · EMQX</div>
              <h1>Giám sát mạng cảm biến LWB</h1>
              <p>{onlineCount} / {allNodes.length} node đang hoạt động · cập nhật mỗi 2 giây · dữ liệu cảm biến giữ {overview?.retention_minutes ?? 15} phút</p>
            </div>
          </div>
          <div className="topbar-right">
            <div className="clock-label">{new Date(clock).toLocaleString('vi-VN', { hour12: false })}</div>
            <GatewayBar gateways={overview?.gateways} />
          </div>
        </header>

        {overviewError && <div className="error-box" role="alert">Không gọi được API ({overviewError}). Kiểm tra cửa sổ "web server" đang chạy.</div>}

        <section className="lwb-section">
          <div className="section-heading">
            <div><span className="eyebrow">MẠNG LWB</span><h3>Các node đang gửi dữ liệu</h3></div>
            <label className="toggle-offline"><input type="checkbox" checked={showOffline} onChange={e => setShowOffline(e.target.checked)} /> Hiện cả node offline</label>
          </div>
          {nodes.length ? (
            <div className="lwb-node-grid">
              {nodes.map(n => <NodeCard key={getNodeKey(n)} node={n} selected={getNodeKey(n) === selectedKey} onSelect={() => setSelectedKey(getNodeKey(n))} />)}
            </div>
          ) : (
            <div className="state-card"><h3>Chưa có node nào online</h3><p>Node sẽ tự xuất hiện khi gửi bản tin đầu tiên. Kiểm tra cửa sổ "mqtt consumer" và gateway trên Raspberry Pi.</p></div>
          )}
        </section>

        <section className="lwb-section history-panel">
          <div className="history-header">
            <div><span className="eyebrow">HIỆU NĂNG GIAO THỨC</span><h3>Kết quả đo LWB theo từng source</h3></div>
          </div>
          <PerfTable perf={perf} onRun={setRun} />
        </section>

        {selected && (
          <section className="lwb-section history-panel">
            <div className="history-header">
              <div><span className="eyebrow">LỊCH SỬ · NODE {pad2(selected.node_id)}</span><h3>Nhiệt độ, độ ẩm, ánh sáng, áp suất và độ trễ</h3></div>
              <div className="range-control">
                {HISTORY_OPTIONS.map(l => <button type="button" key={l} className={historyLimit === l ? 'selected' : ''} onClick={() => setHistoryLimit(l)}>{l} mẫu</button>)}
              </div>
            </div>
            <div className="chart-grid">
              <MiniChart title="Nhiệt độ & độ ẩm" emptyLabel="nhiệt độ / độ ẩm" data={history}
                series={[
                  { key: 'temperature_c', name: 'Nhiệt độ (°C)', color: '#4d77dc', axis: 't', minPad: 0.5 },
                  { key: 'humidity_percent', name: 'Độ ẩm (%)', color: '#16a8a1', axis: 'h', minPad: 1, clamp: [0, 100] },
                ]} />
              <MiniChart title="Ánh sáng (raw)" emptyLabel="ánh sáng" data={history}
                series={[{ key: 'light_raw', name: 'Ánh sáng (raw)', color: '#e0a526', axis: 't', minPad: 1 }]} />
              <MiniChart title="Áp suất (hPa)" emptyLabel="áp suất" data={history}
                series={[{ key: 'pressure_hpa', name: 'Áp suất (hPa)', color: '#8a63d2', axis: 't', minPad: 1 }]} />
              <MiniChart title="Độ trễ enqueue → HOST (ms)" emptyLabel="độ trễ" data={history}
                series={[{ key: 'delay_ms', name: 'Delay (ms)', color: '#e8a34e', axis: 't', minPad: 1, clamp: [0, Infinity] }]} />
            </div>
          </section>
        )}

        <footer className="footer-bar"><span>LWB Environmental Monitoring · Graduation Project</span><span>CC2538 · Raspberry Pi 3 · EMQX · Django REST · React</span></footer>
      </div>
    </div>
  )
}

export default App
