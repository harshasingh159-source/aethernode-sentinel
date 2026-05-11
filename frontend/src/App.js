import React, { useState, useEffect } from 'react';
import './App.css';

// YOUR CLOUDFLARE BRIDGE URL
const API_BASE_URL = "https://distant-initiative-planes-samba.trycloudflare.com";

function App() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState({ total: 0, verified: 0, unknown: 0 });
  const [isOnline, setIsOnline] = useState(false);

  const fetchData = async () => {
    try {
      // 1. Fetch Devices
      const devRes = await fetch(`${API_BASE_URL}/devices`);
      const devData = await devRes.json();
      setDevices(Array.isArray(devData) ? devData : []);

      // 2. Fetch Stats
      const statRes = await fetch(`${API_BASE_URL}/stats`);
      const statData = await statRes.json();
      setStats(statData);
      
      setIsOnline(true);
    } catch (error) { 
      console.error("Bridge Connection Offline:", error); 
      setIsOnline(false);
    }
  };

  const identifyDevice = async (mac) => {
    const name = prompt("Enter identity for this MAC address:");
    if (!name) return;
    try {
      await fetch(`${API_BASE_URL}/update_device`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mac: mac, hostname: name }),
      });
      fetchData(); 
    } catch (error) {
      console.error("Identification failed:", error);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App" style={{ backgroundColor: '#121212', color: '#00ff41', minHeight: '100vh', padding: '20px', fontFamily: 'monospace' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>{">"} AETHER_NODE_SENTINEL_V1.3</h1>
        <div style={{ color: isOnline ? '#00ff41' : '#ff4141' }}>
          ● {isOnline ? "BRIDGE_ACTIVE" : "BRIDGE_OFFLINE"}
        </div>
      </div>
      
      {/* --- STATS BAR --- */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', padding: '15px', border: '1px solid #333', borderRadius: '5px' }}>
        <div>[ TOTAL: <span style={{color: 'white'}}>{stats.total}</span> ]</div>
        <div>[ VERIFIED: <span style={{color: '#00ff41'}}>{stats.verified}</span> ]</div>
        <div>[ UNKNOWN_ALERTS: <span style={{color: '#ff4141'}}>{stats.unknown}</span> ]</div>
      </div>

      <hr style={{ borderColor: '#00ff41' }} />
      
      <div style={{ marginTop: '20px' }}>
        <h2>[ LIVE_NETWORK_MAP ]</h2>
        <table border="1" style={{ width: '100%', borderColor: '#00ff41', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: '#1a1a1a' }}>
              <th style={{ padding: '10px' }}>IDENTITY</th>
              <th>MAC ADDRESS</th>
              <th>IP ADDRESS</th>
              <th>STATUS</th>
              <th>ACTION</th>
            </tr>
          </thead>
          <tbody>
            {devices.length > 0 ? (
              devices.map((dev, index) => (
                <tr key={index} style={{ borderBottom: '1px solid #333', backgroundColor: dev.status === 'Unknown' ? 'rgba(255, 65, 65, 0.05)' : 'transparent' }}>
                  <td style={{ padding: '10px' }}>{dev.hostname || "UNKNOWN_HOST"}</td>
                  <td>{dev.mac}</td>
                  <td>{dev.ip || "0.0.0.0"}</td>
                  <td style={{ color: dev.status === 'Unknown' ? '#ff4141' : '#00ff41', fontWeight: 'bold' }}>
                    {dev.status}
                  </td>
                  <td>
                    <button 
                      onClick={() => identifyDevice(dev.mac)} 
                      style={{ backgroundColor: '#00ff41', color: 'black', border: 'none', cursor: 'pointer', padding: '5px 10px', fontWeight: 'bold' }}
                    >
                      IDENTIFY
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '40px', color: '#666' }}>
                  [ {isOnline ? "NO_DEVICES_IN_DATABASE" : "WAITING_FOR_BRIDGE..."} ]
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default App;