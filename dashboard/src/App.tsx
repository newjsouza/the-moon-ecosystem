import React from 'react';
import { CyberLayout } from './components/CyberLayout';
import { AgentMatrix } from './components/AgentMatrix';
import { LogTerminal } from './components/LogTerminal';
import { CommandUplink } from './components/CommandUplink';
import { IntelligenceHub } from './components/IntelligenceHub';

function App() {
  return (
    <CyberLayout>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-6 h-[calc(100vh-8rem)]">
        {/* Left Column - Agents Matrix */}
        <div className="lg:col-span-4 glass-panel p-4 overflow-hidden flex flex-col gap-4">
          <h2 className="text-[16px] font-mono text-cyber-accent border-b border-cyber-accent/20 pb-2 flex justify-between items-center">
            <span>[ SYSTEM AGENTS ]</span>
            <span className="text-[10px] text-cyber-accent/50 animate-pulse-slow">LIVE SYNC</span>
          </h2>
          <AgentMatrix />
        </div>

        {/* Middle Column - Intelligence Hub */}
        <div className="lg:col-span-5 glass-panel p-4 overflow-hidden flex flex-col gap-4">
          <h2 className="text-[16px] font-mono text-cyber-success border-b border-cyber-success/20 pb-2 flex justify-between items-center">
            <span>[ INTELLIGENCE NEXUS ]</span>
            <span className="text-[10px] text-cyber-success/50 animate-pulse-slow">A.I. TRENDS</span>
          </h2>
          <IntelligenceHub />
        </div>

        {/* Right Column - Logs & Terminal */}
        <div className="lg:col-span-3 glass-panel p-4 overflow-hidden flex flex-col gap-4 cyber-border-purple">
          <h2 className="text-[16px] font-mono text-cyber-purple border-b border-cyber-purple/20 pb-2">
            [ UPLINK TERMINAL ]
          </h2>
          <LogTerminal />
          <CommandUplink />
        </div>
      </div>
    </CyberLayout>
  );
}

export default App;
