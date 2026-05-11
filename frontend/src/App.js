import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [devices, setDevices] = useState([]);
  const [stats, setStats] = useState({ total: 0, verified: 0, unknown: 0 });

  const fetchData = async () => {
    try {
      // 1. Fetch Devices (Updated to handle direct list)
      const devRes = await fetch('http://127.0.0.1:8000/devices');
      const devData = await devRes.json();
      
      // We set devData directly because the API now returns an array []
      setDevices(Array.isArray(devData) ? devData : []);

      // 2. Fetch Stats
      const statRes = await fetch('http://127.0.0.1:8000/stats');
      const statData = await statRes.json();
      setStats(statData);
    } catch (error) { 
      console.error("Connection to AetherNode API failed:", error); 
    }
  };

  const identifyDevice = async (mac) => {
    const name = prompt("Enter a name for this device (e.g., My iPhone, Worldlink Router):");
    if (!name) return;
    try {
      await fetch('http://127.0.0.1:8000/update_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mac: mac, hostname: name }),
      });
      fetchData(); 
    } catch (error) {
      console.error("Update failed:", error);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Auto-refresh every 5 seconds
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="App" style={{ backgroundColor: '#121212', color: '#00ff41', minHeight: '100vh', padding: '20px', fontFamily: 'monospace' }}>
      <h1>{">"} AETHER_NODE_SENTINEL_V1.3</h1>
      
      {/* --- STATS BAR --- */}
      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', padding: '15px', border: '1px solid #333', borderRadius: '5px' }}>
        <div>[ TOTAL_DEVICES: <span style={{color: 'white'}}>{stats.total}</span> ]</div>
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
                <tr key={index} style={{ borderBottom: '1px solid #333' }}>
                  <td style={{ padding: '10px' }}>{dev.hostname || "UNKNOWN_HOST"}</td>
                  <td>{dev.mac}</td>
                  <td>{dev.ip || "0.0.0.0"}</td>
                  <td style={{ color: dev.status === 'Unknown' ? '#ff4141' : '#00ff41', fontWeight: 'bold' }}>
                    {dev.status || "Scanning..."}
                  </td>
                  <td>
                    <button 
                      onClick={() => identifyDevice(dev.mac)} 
                      style={{ backgroundColor: '#00ff41', color: 'black', border: 'none', cursor: 'pointer', padding: '5px 10px', fontWeight: 'bold', borderRadius: '3px' }}
                    >
                      IDENTIFY
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                  [ NO_DEVICES_DETECTED - ENSURE SNIFFER.PY IS RUNNING ]
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