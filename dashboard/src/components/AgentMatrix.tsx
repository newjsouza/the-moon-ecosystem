import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, ShieldAlert, Cpu } from 'lucide-react';

interface AgentData {
  name: string;
  description: string;
  priority: string;
  circuit_breaker: string;
  extra?: Record<string, any>;
}

export function AgentMatrix() {
  const [agents, setAgents] = useState<AgentData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAgents = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/agents');
        const data = await res.json();
        if (data.agents) setAgents(data.agents);
      } catch (err) {
        console.error('Failed to fetch agents:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchAgents();
    const interval = setInterval(fetchAgents, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="text-cyber-accent animate-pulse font-mono">SCANNING NEURAL NET...</div>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 overflow-y-auto pr-2 pb-4">
      {agents.map((agent, index) => {
        const isCritical = agent.priority === 'CRITICAL';
        const isOffline = agent.circuit_breaker === 'open';

        return (
          <motion.div
            key={agent.name}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: Math.min(index * 0.05, 0.5) }}
            className={`glass-panel p-4 flex flex-col gap-3 relative overflow-hidden ${
              isOffline ? 'border-cyber-danger shadow-[0_0_10px_rgba(255,0,60,0.4)]' : 'hover:cyber-border-cyan transition-all'
            }`}
          >
            {/* Background glow for critical */}
            {isCritical && !isOffline && (
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-cyber-accent/10 rounded-full blur-3xl pointer-events-none" />
            )}
            
            <div className="flex justify-between items-start">
              <div className="flex items-center gap-2 min-w-0 mr-2">
                <Cpu className={`flex-shrink-0 w-5 h-5 ${isOffline ? 'text-cyber-danger pulse-fast' : 'text-cyber-accent'}`} />
                <h3 className="font-bold text-gray-100 tracking-wide truncate" title={agent.name}>
                  {agent.name.replace('Agent', '')}
                </h3>
              </div>
              
              <div className="flex items-center gap-2 flex-shrink-0">
                {isOffline ? (
                  <span className="flex items-center justify-center gap-1 text-[10px] text-cyber-danger bg-cyber-danger/10 px-2 rounded border border-cyber-danger/20 font-bold leading-none h-6">
                    <ShieldAlert className="w-3 h-3 animate-pulse" /> OFFLINE
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-1 text-[10px] text-cyber-success bg-cyber-success/10 px-2 rounded border border-cyber-success/20 font-bold leading-none h-6">
                    <Activity className="w-3 h-3" /> {agent.priority}
                  </span>
                )}
              </div>
            </div>

            <p className="text-xs text-gray-400 line-clamp-2 title font-mono h-[32px]">
              {agent.description || 'Core autonomy subsystem.'}
            </p>

            {agent.extra && Object.keys(agent.extra).length > 0 && (
              <div className="mt-1 pt-2 border-t border-gray-800 text-[10px] text-gray-500 font-mono truncate">
                INITIATIVE: {agent.extra.current_initiative || 'STANDBY'}
              </div>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}
