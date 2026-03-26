import React from 'react';
import { AgentMatrix } from '../components/AgentMatrix';

export function DashboardView() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">
      {/* Left Column - Large Agents Matrix */}
      <div className="lg:col-span-8 glass-panel p-6 overflow-hidden flex flex-col gap-4 relative">
        <h2 className="text-lg font-mono text-cyber-accent border-b border-cyber-accent/20 pb-2 flex justify-between items-center z-10">
          <span>[ SYSTEM AGENTS STATUS ]</span>
          <span className="text-xs text-cyber-accent/50 animate-pulse-slow">LIVE SYNC</span>
        </h2>
        <AgentMatrix />
        {/* Decorative Grid Overlay */}
        <div className="absolute inset-0 pointer-events-none opacity-[0.03] cyber-grid" />
      </div>

      {/* Right Column - System Stats / Summaries */}
      <div className="lg:col-span-4 flex flex-col gap-6">
        <div className="glass-panel p-6 flex-1 flex flex-col gap-4">
          <h2 className="text-lg font-mono text-white border-b border-white/10 pb-2">
            [ SYSTEM PARAMS ]
          </h2>
          <div className="flex flex-col gap-4 font-mono text-xs text-gray-400">
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span>CORE ARCHITECTURE:</span>
              <span className="text-cyber-accent">ASYNCHRONOUS</span>
            </div>
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span>ORCHESTRATOR UPTIME:</span>
              <span className="text-cyber-success">99.9%</span>
            </div>
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span>MEMORY ALLOCATION:</span>
              <span className="text-cyber-purple">DYNAMIC</span>
            </div>
            <div className="flex justify-between border-b border-white/5 pb-2">
              <span>SECURITY PROTOCOL:</span>
              <span className="text-white">ENFORCED</span>
            </div>
          </div>
        </div>
        
        <div className="glass-panel p-6 h-48 flex flex-col gap-2 relative overflow-hidden group">
          <h2 className="text-lg font-mono text-cyber-accent">
            [ ACTIVE PROTOCOLS ]
          </h2>
          <div className="text-xs font-mono text-cyber-accent/60 mt-2 space-y-2">
            <p>{'>'} Auto-rectification loop: ACTIVE</p>
            <p>{'>'} Telegram listener: BOUND</p>
            <p>{'>'} Threat analysis: STANDBY</p>
          </div>
          <div className="absolute right-4 bottom-4 w-16 h-16 border border-cyber-accent/20 rounded-full flex items-center justify-center animate-[spin_10s_linear_infinite]">
            <div className="w-8 h-8 border border-t-cyber-accent border-r-transparent rounded-full" />
          </div>
        </div>
      </div>
    </div>
  );
}
