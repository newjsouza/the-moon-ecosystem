import React, { useEffect, useState, useRef } from 'react';
import { Terminal } from 'lucide-react';

export function LogTerminal() {
  const [logs, setLogs] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sse = new EventSource('http://localhost:8000/api/logs/stream');
    
    sse.onmessage = (e) => {
      setLogs((prev) => {
        const next = [...prev, e.data];
        if (next.length > 200) return next.slice(next.length - 200);
        return next;
      });
    };

    return () => {
      sse.close();
    };
  }, []);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-black/40 rounded-lg border border-gray-800/50 relative overflow-hidden">
      <div className="absolute top-0 w-full h-8 bg-gradient-to-b from-cyber-purple/10 to-transparent pointer-events-none" />
      <div className="flex items-center gap-2 px-3 py-2 border-b border-cyber-purple/20 bg-cyber-purple/5">
        <Terminal className="w-4 h-4 text-cyber-purple" />
        <span className="text-xs font-mono text-cyber-purple uppercase tracking-wider">
          System.Log.Stream
        </span>
      </div>
      
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-5">
        {logs.map((log, i) => {
          let colorClass = 'text-gray-400';
          if (log.includes('ERROR') || log.includes('❌')) colorClass = 'text-cyber-danger font-bold';
          if (log.includes('WARNING') || log.includes('⚠️')) colorClass = 'text-yellow-400';
          if (log.includes('INFO') || log.includes('✅')) colorClass = 'text-cyber-accent';
          
          return (
            <div key={i} className={`whitespace-pre-wrap break-words ${colorClass}`}>
              {log}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
