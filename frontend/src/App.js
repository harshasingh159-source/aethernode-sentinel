import React, { useState, useEffect, useCallback, useMemo } from 'react';
import './App.css';

// Set REACT_APP_API_URL in frontend/.env (e.g. a Cloudflare tunnel URL) to point at a remote API.
const API_BASE_URL = (process.env.REACT_APP_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const POLL_MS = 5000;

function timeAgo(ts) {
  if (!ts) return '—';
  const secs = Math.max(0, (Date.now() - new Date(ts.replace(' ', 'T')).getTime()) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

async function api(path, options) {
  const res = await fetch(`${API_BASE_URL}${path}`, options);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function DeviceRow({ dev, onSave, onRevoke, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(dev.hostname || '');
  const unknown = dev.status !== 'Verified';

  const submit = (e) => {
    e.preventDefault();
    if (name.trim()) onSave(dev.mac, name.trim()).then(() => setEditing(false));
  };

  return (
    <tr className={unknown ? 'intruder-row' : ''}>
      <td>
        {editing ? (
          <form onSubmit={submit} className="inline-form">
            <input autoFocus value={name} maxLength={64} onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && setEditing(false)} placeholder="device name" />
            <button type="submit" className="btn">SAVE</button>
          </form>
        ) : (
          <span className={dev.hostname ? '' : 'muted'}>{dev.hostname || 'UNKNOWN_HOST'}</span>
        )}
      </td>
      <td className="mono">{dev.mac}</td>
      <td>{dev.vendor || <span className="muted">—</span>}</td>
      <td>{dev.ip || '0.0.0.0'}</td>
      <td title={dev.last_seen}>
        <span className={`dot ${dev.online ? 'on' : 'off'}`} />
        {timeAgo(dev.last_seen)}
      </td>
      <td className={unknown ? 'status-bad' : 'status-ok'}>{dev.status}</td>
      <td className="actions">
        <button className="btn" onClick={() => setEditing(!editing)}>
          {unknown ? 'IDENTIFY' : 'RENAME'}
        </button>
        {!unknown && <button className="btn ghost" onClick={() => onRevoke(dev.mac)}>REVOKE</button>}
        <button className="btn danger" onClick={() => onDelete(dev.mac)}>✕</button>
      </td>
    </tr>
  );
}

function App() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState({ total: 0, verified: 0, unknown: 0, online: 0 });
  const [isOnline, setIsOnline] = useState(false);
  const [filter, setFilter] = useState('');
  const [view, setView] = useState('all');
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      const [devData, statData] = await Promise.all([api('/devices'), api('/stats')]);
      setDevices(Array.isArray(devData) ? devData : []);
      setStats(statData);
      setIsOnline(true);
    } catch (err) {
      console.error('Bridge Connection Offline:', err);
      setIsOnline(false);
    }
  }, []);

  const act = (fn) => async (...args) => {
    try {
      setError('');
      await fn(...args);
      await fetchData();
    } catch (err) {
      setError(`Action failed: ${err.message}`);
    }
  };

  const saveName = act((mac, hostname) => api('/update_device', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac, hostname }),
  }));
  const revoke = act((mac) => api(`/devices/${encodeURIComponent(mac)}/revoke`, { method: 'POST' }));
  const remove = act((mac) => window.confirm(`Remove ${mac} from the database?`)
    && api(`/devices/${encodeURIComponent(mac)}`, { method: 'DELETE' }));

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, POLL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    document.title = stats.unknown > 0 ? `(${stats.unknown}) ⚠ AetherNode` : 'AetherNode Sentinel';
  }, [stats.unknown]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return devices.filter((d) => {
      if (view === 'unknown' && d.status === 'Verified') return false;
      if (view === 'online' && !d.online) return false;
      if (!q) return true;
      return [d.hostname, d.mac, d.ip, d.vendor].some((v) => v && v.toLowerCase().includes(q));
    });
  }, [devices, filter, view]);

  return (
    <div className="App">
      <header className="header">
        <h1>{'>'} AETHER_NODE_SENTINEL_V1.4</h1>
        <div className={isOnline ? 'status-ok' : 'status-bad'}>
          ● {isOnline ? 'BRIDGE_ACTIVE' : 'BRIDGE_OFFLINE'}
        </div>
      </header>

      <div className="stats">
        <div>[ TOTAL: <b className="white">{stats.total}</b> ]</div>
        <div>[ ONLINE: <b className="white">{stats.online}</b> ]</div>
        <div>[ VERIFIED: <b className="status-ok">{stats.verified}</b> ]</div>
        <div className={stats.unknown > 0 ? 'alert' : ''}>
          [ UNKNOWN_ALERTS: <b className="status-bad">{stats.unknown}</b> ]
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <section>
        <div className="toolbar">
          <h2>[ LIVE_NETWORK_MAP ]</h2>
          <div className="controls">
            {['all', 'online', 'unknown'].map((v) => (
              <button key={v} className={`btn ${view === v ? '' : 'ghost'}`} onClick={() => setView(v)}>
                {v.toUpperCase()}
              </button>
            ))}
            <input className="search" placeholder="search name / mac / ip / vendor"
              value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>IDENTITY</th><th>MAC ADDRESS</th><th>VENDOR</th><th>IP ADDRESS</th>
                <th>LAST SEEN</th><th>STATUS</th><th>ACTION</th>
              </tr>
            </thead>
            <tbody>
              {visible.length > 0 ? (
                visible.map((dev) => (
                  <DeviceRow key={dev.mac} dev={dev} onSave={saveName} onRevoke={revoke} onDelete={remove} />
                ))
              ) : (
                <tr>
                  <td colSpan="7" className="empty">
                    [ {!isOnline ? `WAITING_FOR_BRIDGE @ ${API_BASE_URL}`
                      : devices.length ? 'NO_MATCHES' : 'NO_DEVICES_IN_DATABASE — START sniffer.py'} ]
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

export default App;
