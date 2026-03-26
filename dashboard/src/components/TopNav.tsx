import React from 'react';
import { Network, BrainCircuit, TerminalSquare, Settings } from 'lucide-react';
import clsx from 'clsx';

interface TopNavProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export function TopNav({ activeTab, setActiveTab }: TopNavProps) {
  const tabs = [
    { id: 'dashboard', label: 'SYSTEM MATRIX', icon: Network, color: 'text-cyber-accent', bgColor: 'bg-cyber-accent' },
    { id: 'automations', label: 'AUTOMATIONS', icon: Settings, color: 'text-cyber-success', bgColor: 'bg-cyber-success' }
  ];

  return (
    <div className="w-full h-16 glass-panel border-b border-white/5 mb-6 px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 rounded bg-cyber-accent/20 border border-cyber-accent flex items-center justify-center animate-pulse-slow flex-shrink-0">
          <Network className="w-5 h-5 text-cyber-accent" />
        </div>
        <div className="flex flex-col">
          <h1 className="text-xl font-mono font-bold text-white tracking-widest leading-none">THE MOON</h1>
          <span className="text-[10px] text-cyber-accent font-mono uppercase tracking-[0.2em] mt-0.5">Cyber-Agentic OS</span>
        </div>
      </div>

      <div className="flex items-center justify-center flex-1 h-full mx-8">
        <div className="flex items-center gap-2 h-full">
          {tabs.map(tab => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  "relative h-full px-6 flex items-center justify-center gap-2 font-mono text-sm transition-all duration-300",
                  isActive ? "text-white" : "text-gray-500 hover:text-white"
                )}
              >
                <Icon className={clsx("w-4 h-4", isActive ? tab.color : "")} />
                <span className="tracking-widest">{tab.label}</span>
                {isActive && (
                  <div className={clsx("absolute bottom-0 left-0 w-full h-[2px] shadow-[0_0_10px_currentColor]", tab.bgColor)} />
                )}
              </button>
            );
          })}
        </div>
      </div>
      
      <div className="flex items-center gap-2 flex-shrink-0">
        <span className="w-2 h-2 rounded-full bg-cyber-success shadow-[0_0_8px_#39ff14] animate-pulse"></span>
        <span className="text-xs font-mono text-cyber-success tracking-widest">SYS.ONLINE</span>
      </div>
    </div>
  );
}
