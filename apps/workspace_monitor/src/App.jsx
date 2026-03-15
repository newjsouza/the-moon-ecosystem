import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Activity, 
  Terminal, 
  Cpu, 
  Network, 
  Settings, 
  Box, 
  Zap,
  LayoutDashboard,
  MessageSquare
} from 'lucide-react';

const SOCKET_URL = `ws://${window.location.hostname}:8081/ws`;

export default function App() {
  const [rooms, setRooms] = useState({});
  const [logs, setLogs] = useState([]);
  const [pulses, setPulses] = useState([]);
  const [connected, setConnected] = useState(false);
  const logEndRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(SOCKET_URL);

    ws.onopen = () => {
      setConnected(true);
      console.log('Connected to Monitor Backend');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'init') {
        setRooms(data.rooms);
      } else if (data.type === 'message') {
        const { sender, target, payload, timestamp } = data;
        
        // Add pulse animation
        const pulseId = Math.random().toString(36).substr(2, 9);
        setPulses(prev => [...prev, { id: pulseId, sender, target }]);
        setTimeout(() => {
          setPulses(prev => prev.filter(p => p.id !== pulseId));
        }, 1500);

        // Add log
        const logEntry = {
          id: pulseId,
          timestamp: new Date(timestamp * 1000).toLocaleTimeString(),
          sender,
          target: target || 'Broadcast',
          text: payload
        };
        setLogs(prev => [logEntry, ...prev].slice(0, 100));
      }
    };

    ws.onclose = () => setConnected(false);
    return () => ws.close();
  }, []);

  useEffect(() => {
    // Periodically fetch state to sync
    const fetchStatus = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8081/api/status`);
        const data = await res.json();
        setRooms(data.rooms);
      } catch (err) {
        console.error('Failed to fetch status', err);
      }
    };
    
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const roomList = Object.values(rooms);
  
  // Calculate positions for nodes in a circle
  const getPosition = (index, total) => {
    const radius = 250;
    const angle = (index / total) * 2 * Math.PI;
    const x = Math.cos(angle) * radius + 250;
    const y = Math.sin(angle) * radius + 250;
    return { x, y };
  };

  return (
    <div className="dashboard-grid">
      <header className="header glass border-glow-cyan">
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <div className={`status-indicator ${connected ? 'pulse' : ''}`} 
               style={{ width: 12, height: 12, borderRadius: '50%', background: connected ? '#00f2ff' : '#ff4444' }}></div>
          <h1>THE MOON <span style={{ fontSize: '0.8rem', opacity: 0.5 }}>WORKSPACE_MONITOR v1.0</span></h1>
        </div>
        <div style={{ display: 'flex', gap: '20px' }}>
          <Activity size={20} className="glow-cyan" />
          <Settings size={20} />
        </div>
      </header>

      <aside className="sidebar-left glass border-glow-cyan">
        <div style={{ padding: '20px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Box size={18} color="#00f2ff" /> SALAS ATIVAS
          </h3>
        </div>
        <div style={{ padding: '15px', overflowY: 'auto' }}>
          {roomList.map(room => (
            <div key={room.room_id} className="glass" style={{ padding: '12px', marginBottom: '10px', borderRadius: '8px', border: 'none', background: 'rgba(255,255,255,0.03)' }}>
              <div style={{ fontWeight: 'bold', fontSize: '0.9rem', marginBottom: '5px' }}>{room.room_id.toUpperCase()}</div>
              <div style={{ fontSize: '0.75rem', color: '#9494b8' }}>Líder: {room.leader}</div>
              <div style={{ display: 'flex', gap: '10px', marginTop: '8px' }}>
                <Cpu size={14} color={room.computer_ready ? '#00f2ff' : '#444'} />
                <Network size={14} color="#00f2ff" />
              </div>
            </div>
          ))}
        </div>
      </aside>

      <main className="main-map glass border-glow-cyan" style={{ position: 'relative' }}>
        <div style={{ position: 'absolute', top: '20px', left: '20px', zIndex: 5 }}>
          <LayoutDashboard size={20} style={{ opacity: 0.3 }} />
        </div>
        
        {/* Connection Lines (SVGs would be better, but we use a simpler approach for now) */}
        <svg style={{ position: 'absolute', width: '100%', height: '100%', pointerEvents: 'none' }}>
           {/* Connection lines would go here */}
        </svg>

        <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: 600, height: 600 }}>
          <AnimatePresence>
            {roomList.map((room, idx) => {
              const pos = getPosition(idx, roomList.length);
              return (
                <motion.div
                  key={room.room_id}
                  className="node"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1, left: pos.x, top: pos.y }}
                  transition={{ type: 'spring', damping: 15 }}
                >
                  <Cpu size={24} color="#00f2ff" />
                  <div className="node-label" style={{ color: '#00f2ff' }}>{room.room_id.toUpperCase()}</div>
                </motion.div>
              );
            })}
          </AnimatePresence>

          {/* Pulse Animations */}
          {pulses.map(pulse => {
            const senderIdx = roomList.findIndex(r => r.room_id === (pulse.sender.toLowerCase().replace(' ', '_')));
            const targetIdx = roomList.findIndex(r => r.room_id === (pulse.target?.toLowerCase().replace(' ', '_')));
            
            if (senderIdx === -1) return null;
            
            const start = getPosition(senderIdx, roomList.length);
            
            if (targetIdx !== -1) {
              const end = getPosition(targetIdx, roomList.length);
              return (
                <motion.div
                  key={pulse.id}
                  initial={{ left: start.x + 30, top: start.y + 30, scale: 0 }}
                  animate={{ left: end.x + 30, top: end.y + 30, scale: [0, 1.5, 0] }}
                  transition={{ duration: 1, ease: "easeInOut" }}
                  style={{ position: 'absolute', width: 10, height: 10, background: '#00f2ff', borderRadius: '50%', zIndex: 20, filter: 'blur(2px)' }}
                />
              );
            } else {
              // Broadcast
              return (
                <motion.div
                  key={pulse.id}
                  initial={{ left: start.x + 30, top: start.y + 30, scale: 0, opacity: 1 }}
                  animate={{ scale: 20, opacity: 0 }}
                  transition={{ duration: 1 }}
                  style={{ position: 'absolute', width: 40, height: 40, border: '2px solid #ff00ff', borderRadius: '50%', zIndex: 1, transform: 'translate(-50%, -50%)' }}
                />
              );
            }
          })}
        </div>
      </main>

      <aside className="sidebar-right glass border-glow-cyan">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
          <Terminal size={18} color="#00f2ff" /> LOGS DE REDE
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {logs.map(log => (
            <div key={log.id} className="log-item">
              <span className="log-timestamp">[{log.timestamp}]</span>
              <span style={{ color: '#ff00ff' }}>{log.sender}</span> -&gt; <span>{log.target}</span>: {log.text}
            </div>
          ))}
          {logs.length === 0 && <div className="log-item" style={{ opacity: 0.3 }}>Aguardando interações...</div>}
        </div>
      </aside>

      <footer className="footer glass border-glow-cyan">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', gap: '20px', color: '#9494b8', fontSize: '0.8rem' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}><Zap size={14} color="#00f2ff" /> Memória: 24.5 GiB</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}><MessageSquare size={14} color="#00f2ff" /> Mensagens: {logs.length}</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#444' }}>OPEN_CLAW INTERFACE</div>
        </div>
      </footer>
    </div>
  );
}
