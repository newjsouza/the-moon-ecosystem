/* React import removed */
import { LogTerminal } from '../components/LogTerminal';
import { CommandUplink } from '../components/CommandUplink';

export function TerminalView() {
  return (
    <div className="grid grid-cols-1 gap-6 h-full flex-1">
      <div className="glass-panel p-6 flex flex-col gap-6 cyber-border-purple h-full">
        <h2 className="text-xl font-mono text-cyber-purple border-b border-cyber-purple/20 pb-4">
          [ DIRECT UPLINK & SYSTEM TERMINAL ]
        </h2>
        
        {/* Make the terminal take most of the height */}
        <div className="flex-1 min-h-0 bg-black/80 rounded border border-cyber-purple/20 p-2 overflow-hidden shadow-[inset_0_0_20px_rgba(176,38,255,0.1)]">
          <LogTerminal />
        </div>
        
        {/* Command Injection */}
        <div className="h-16 flex-shrink-0">
          <CommandUplink />
        </div>
      </div>
    </div>
  );
}
