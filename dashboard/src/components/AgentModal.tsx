import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Activity, Cpu, Zap, ServerCrash } from 'lucide-react';
import clsx from 'clsx';

interface AgentDetails {
  name: string;
  description: string;
  priority: string;
  status: string;
  failures: number;
  memory: any[];
  current_task: string | null;
}

interface AgentModalProps {
  agentName: string | null;
  onClose: () => void;
}

export function AgentModal({ agentName, onClose }: AgentModalProps) {
  const [details, setDetails] = useState<AgentDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!agentName) return;
    setLoading(true);
    fetch(`http://localhost:8000/api/agents/${agentName}`)
      .then(res => res.json())
      .then(data => setDetails(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [agentName]);

  const sendAction = async (action: string) => {
    if (!agentName) return;
    setActionStatus(`Sending ${action}...`);
    try {
      const res = await fetch(`http://localhost:8000/api/agents/${agentName}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const data = await res.json();
      setActionStatus(data.message || 'Success');
      setTimeout(() => setActionStatus(null), 3000);
    } catch (e) {
      setActionStatus('Failed to send action');
    }
  };

  if (!agentName) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          className="relative w-full max-w-2xl bg-[#05050A] border rounded-lg shadow-2xl flex flex-col font-mono overflow-hidden border-cyber-accent/30 shadow-[0_0_30px_rgba(0,240,255,0.1)]"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-white/10 bg-white/5">
            <div className="flex items-center gap-3">
              <Cpu className={clsx("w-6 h-6", details?.status === 'offline' ? 'text-cyber-danger pulse-fast' : 'text-cyber-accent')} />
              <h2 className="text-xl font-bold text-white tracking-widest">{agentName}</h2>
            </div>
            <button onClick={onClose} className="p-2 text-gray-400 hover:text-white transition-colors rounded hover:bg-white/10">
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 flex flex-col gap-6">
            {loading || !details ? (
              <div className="text-center text-cyber-accent animate-pulse py-10">SYNCING AGENT DATA...</div>
            ) : (
              <>
                <div className="flex flex-wrap gap-4 text-xs">
                  <div className={clsx("flex items-center gap-2 px-3 py-1.5 rounded border font-bold tracking-wider", details.status === 'online' ? "border-cyber-success/30 bg-cyber-success/10 text-cyber-success" : "border-cyber-danger/30 bg-cyber-danger/10 text-cyber-danger")}>
                    {details.status === 'online' ? <Activity className="w-4 h-4" /> : <ServerCrash className="w-4 h-4" />}
                    STATUS: {details.status.toUpperCase()}
                  </div>
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded border border-white/10 bg-white/5 text-gray-300 font-bold tracking-wider">
                    PRIORITY: {details.priority}
                  </div>
                  {details.failures > 0 && (
                    <div className="flex items-center gap-2 px-3 py-1.5 rounded border border-yellow-500/30 bg-yellow-500/10 text-yellow-400 font-bold tracking-wider">
                      FAILURES: {details.failures}
                    </div>
                  )}
                </div>

                <div className="text-sm text-gray-400 leading-relaxed">
                  {details.description}
                </div>

                <div className="flex flex-col gap-2">
                  <h3 className="text-xs font-bold text-cyber-accent border-b border-cyber-accent/20 pb-1">RECENT RECALL (MEMORY)</h3>
                  <div className="bg-black/50 border border-white/10 rounded p-3 h-32 overflow-y-auto custom-scrollbar text-[10px] text-gray-400 leading-tight space-y-2">
                    {details.memory && details.memory.length > 0 ? (
                      details.memory.map((m, i) => (
                        <div key={i} className="border-l-2 border-cyber-accent pl-2">
                          <span className="text-cyber-accent/50 mr-2">[{new Date(m.timestamp * 1000).toLocaleTimeString()}]</span>
                          {m.type || 'EVENT'}: {JSON.stringify(m.data).slice(0, 100)}
                        </div>
                      ))
                    ) : (
                      <span className="opacity-50">NO RECENT MEMORY DETECTED</span>
                    )}
                  </div>
                </div>

                {/* Uplink Actions */}
                <div className="flex items-center justify-between pt-4 border-t border-white/10">
                  <div className="text-xs text-cyber-success/80 h-4">
                    {actionStatus && `>= ${actionStatus}`}
                  </div>
                  <div className="flex gap-3">
                    <button onClick={() => sendAction('ping')} className="px-4 py-2 text-xs font-bold rounded flex items-center justify-center gap-2 tracking-widest text-cyber-accent border border-cyber-accent/30 hover:bg-cyber-accent/10 transition-colors">
                      <Zap className="w-3 h-3" /> PING
                    </button>
                    <button onClick={() => sendAction('force_run')} className="px-4 py-2 text-xs font-bold rounded flex items-center justify-center gap-2 tracking-widest text-black bg-cyber-accent hover:bg-cyber-accent/80 transition-colors shadow-[0_0_15px_rgba(0,240,255,0.3)]">
                      <Activity className="w-3 h-3" /> FORCE CYCLE
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
