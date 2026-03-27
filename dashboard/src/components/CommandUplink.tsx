import { useState } from 'react';
import { TerminalSquare, Send } from 'lucide-react';

export function CommandUplink() {
  const [command, setCommand] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!command.trim()) return;

    setLoading(true);
    try {
      await fetch('http://localhost:8000/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
      });
      setCommand('');
    } catch (err) {
      console.error('Failed to send command:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="mt-auto shrink-0 border border-cyber-purple/20 bg-black/50 p-3 rounded flex gap-3 relative group">
      {/* Background glow on focus/hover */}
      <div className="absolute inset-0 bg-cyber-purple/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
      
      <div className="flex items-center justify-center p-2">
        <TerminalSquare className="w-5 h-5 text-cyber-purple" />
      </div>

      <input
        type="text"
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        placeholder="ENTER DIRECTIVE..."
        className="flex-1 bg-transparent border-none outline-none text-cyber-purple font-mono placeholder-cyber-purple/30 text-sm placeholder:tracking-widest"
        disabled={loading}
      />

      <button
        type="submit"
        disabled={loading || !command.trim()}
        className="bg-transparent hover:bg-cyber-purple/10 text-cyber-purple rounded p-2 flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed group"
      >
        <Send className="w-4 h-4 group-hover:drop-shadow-[0_0_8px_#b026ff]" />
      </button>
    </form>
  );
}
