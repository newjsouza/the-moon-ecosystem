/* React import removed */
import { IntelligenceHub } from '../components/IntelligenceHub';

export function IntelligenceView() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-full">
      {/* Left panel - Info */}
      <div className="lg:col-span-1 glass-panel p-6 flex flex-col gap-6 border-cyber-success/30">
        <h2 className="text-lg font-mono text-cyber-success border-b border-cyber-success/20 pb-2">
          [ INTELLIGENCE OPS ]
        </h2>
        <div className="text-sm text-gray-400 font-mono leading-relaxed">
          <p className="mb-4">
            The Moon conducts independent research cycles to synthesize industry
            trends and competitive intelligence.
          </p>
          <p className="text-cyber-success/80 mb-2">{'>'} Active Trackers:</p>
          <ul className="list-disc pl-4 space-y-1">
            <li>OpenAI / ChatGPT</li>
            <li>Anthropic Claude</li>
            <li>Google Gemini</li>
            <li>xAI Groq</li>
            <li>DeepSeek / Alibaba</li>
          </ul>
        </div>
        
        <div className="mt-auto glass-panel p-4 flex flex-col gap-2 items-center justify-center bg-cyber-success/5 border border-cyber-success/20 group hover:bg-cyber-success/10 transition-colors">
          <div className="text-cyber-success text-2xl font-bold animate-pulse-slow">A.I.</div>
          <p className="text-xs text-center text-cyber-success/70 font-mono">Continuous Synthesis</p>
        </div>
      </div>

      {/* Main panel - Reports */}
      <div className="lg:col-span-3 glass-panel p-6 flex flex-col gap-4 border-cyber-success/30 h-full overflow-hidden">
        <h2 className="text-lg font-mono text-cyber-success border-b border-cyber-success/20 pb-2 flex justify-between">
          <span>[ LATEST INTELLIGENCE REPORTS ]</span>
          <span className="text-xs animate-pulse">SYNCING...</span>
        </h2>
        <div className="flex-1 min-h-0 bg-black/40 rounded border border-cyber-success/10 p-2">
          <IntelligenceHub />
        </div>
      </div>
    </div>
  );
}
