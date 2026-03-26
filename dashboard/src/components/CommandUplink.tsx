import React, { useState } from 'react';
import { Send, TerminalSquare } from 'lucide-react';
import { motion } from 'framer-motion';

export function CommandUplink() {
  const [cmd, setCmd] = useState('');
  const [isSending, setIsSending] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cmd.trim() || isSending) return;
    
    setIsSending(true);
    try {
      await fetch('http://localhost:8000/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd, target_agent: 'orchestrator' })
      });
      setCmd('');
    } catch (err) {
      console.error('Failed to send command', err);
    } finally {
      setIsSending(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="relative mt-auto h-12 flex-shrink-0 group">
      <div className="absolute inset-0 bg-cyber-purple/10 rounded-lg blur-md group-focus-within:bg-cyber-purple/30 transition-all"></div>
      <div className="relative h-full flex items-center bg-black/50 border border-cyber-purple/30 rounded-lg overflow-hidden group-focus-within:border-cyber-purple ring-1 ring-transparent group-focus-within:ring-cyber-purple/50 transition-all">
        <div className="px-3 text-cyber-purple">
          <TerminalSquare className="w-5 h-5" />
        </div>
        <input 
          type="text" 
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          placeholder="ENTER DIRECTIVE..." 
          className="flex-1 bg-transparent border-none outline-none text-cyber-purple font-mono placeholder-cyber-purple/30 w-full px-2 py-2"
          autoComplete="off"
        />
        <button 
          type="submit" 
          disabled={!cmd.trim() || isSending}
          className="h-full w-14 flex-shrink-0 flex items-center justify-center text-cyber-purple hover:bg-cyber-purple/20 disabled:opacity-50 transition-colors"
        >
          {isSending ? (
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
              <div className="w-4 h-4 border-2 border-cyber-purple border-t-transparent rounded-full" />
            </motion.div>
          ) : (
            <Send className="w-4 h-4" />
          )}
        </button>
      </div>
    </form>
  );
}
