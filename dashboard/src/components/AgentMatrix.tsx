import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, ServerCrash, Cpu } from 'lucide-react';
import clsx from 'clsx';
import { AgentModal } from './AgentModal';

interface AgentData {
  name: string;
  status: 'online' | 'offline';
  priority: string;
}

export function AgentMatrix() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/health');
        const json = await res.json();
        
        const agentNames = json.orchestrator_status?.agents || [];
        const mappedAgents: AgentData[] = agentNames.map((name: string) => ({
          name,
          status: 'online', 
          priority: 'NORMAL', 
        }));
        setAgents(mappedAgents);
      } catch (err) {
        console.error('Failed to fetch agents:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="text-cyber-accent animate-pulse font-mono">SCANNING NEURAL NET...</div>;
  }

  return (
    <div className="flex-1 overflow-y-auto pr-2 pb-4 grid grid-cols-2 lg:grid-cols-3 gap-3 custom-scrollbar content-start">
      {agents.map((agent, idx) => (
          <motion.button
            key={agent.name}
            onClick={() => setSelectedAgent(agent.name)}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: idx * 0.05 }}
            className={clsx(
              "glass-panel text-left p-4 flex flex-col gap-3 relative overflow-hidden group cursor-pointer transition-all hover:scale-[1.02] active:scale-[0.98]",
              agent.status === 'online' 
                ? "border-cyber-accent/20 hover:border-cyber-accent/50 shadow-[0_0_10px_rgba(0,240,255,0.05)]" 
                : "border-cyber-danger/40 shadow-[0_0_15px_rgba(255,0,60,0.15)] bg-red-900/10"
            )}
          >
            <div className={clsx(
              "absolute right-0 top-0 bottom-0 w-1",
              agent.status === 'online' ? "bg-cyber-accent/30" : "bg-cyber-danger/60"
            )} />

            <div className="flex items-center gap-2">
              <Cpu className={clsx("w-4 h-4 flex-shrink-0", agent.status === 'online' ? "text-cyber-accent" : "text-cyber-danger pulse-fast")} />
              <span className="font-mono text-xs font-bold tracking-widest text-white truncate w-full">
                {agent.name.toUpperCase()}
              </span>
            </div>

            <div className="flex items-center gap-2 mt-auto pt-2">
              {agent.status === 'online' ? (
                <div className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded bg-cyber-success/10 border border-cyber-success/30 text-cyber-success font-mono text-[10px] sm:text-[11px]">
                  <Activity className="w-3 h-3 flex-shrink-0" />
                  <span className="font-bold tracking-wider">{agent.priority.toUpperCase()}</span>
                </div>
              ) : (
                <div className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded bg-cyber-danger/10 border border-cyber-danger/40 text-cyber-danger font-mono text-[10px] sm:text-[11px] animate-pulse">
                  <ServerCrash className="w-3 h-3 flex-shrink-0" />
                  <span className="font-bold tracking-wider">OFFLINE</span>
                </div>
              )}
            </div>
          </motion.button>
      ))}
      <AgentModal agentName={selectedAgent} onClose={() => setSelectedAgent(null)} />
    </div>
  );
}
