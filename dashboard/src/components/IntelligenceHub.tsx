import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BrainCircuit } from 'lucide-react';

interface ReportData {
  key: string;
  type: string;
  timestamp: number;
  data: {
    topics?: string[];
    findings?: string[];
    report?: string;
  };
}

export function IntelligenceHub() {
  const [reports, setReports] = useState<ReportData[]>([]);

  useEffect(() => {
    const fetchReports = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/reports');
        const json = await res.json();
        if (json.reports) setReports(json.reports);
      } catch (err) {
        console.error('Failed to fetch reports:', err);
      }
    };
    
    fetchReports();
    const interval = setInterval(fetchReports, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex-1 overflow-y-auto pr-2 pb-4 flex flex-col gap-4 custom-scrollbar">
      {reports.length === 0 ? (
        <div className="text-gray-500 font-mono text-sm text-center py-4">
          Awaiting Intelligence Sweeps...
        </div>
      ) : (
        reports.map((report, idx) => (
          <motion.div
            key={report.key || idx}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            className="glass-panel p-4 flex flex-col gap-2 relative overflow-hidden group shadow-[0_0_15px_rgba(57,255,20,0.05)] border-cyber-success/20"
          >
            <div className="flex items-center gap-2 border-b border-cyber-success/20 pb-2">
              <BrainCircuit className="w-4 h-4 text-cyber-success" />
              <span className="text-xs font-mono text-cyber-success uppercase">
                Tech Intel // {new Date(report.timestamp * 1000).toLocaleString('pt-BR')}
              </span>
            </div>
            
            <div className="text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-1 leading-5">
              {report.data?.report || 
                (Array.isArray(report.data?.findings) 
                  ? report.data.findings.map((f: string, i: number) => <div key={i} className="mb-2">👉 {f}</div>) 
                  : (report.data?.findings !== undefined ? `Findings count: ${report.data.findings}` : 'Processing Data...'))}
            </div>
          </motion.div>
        ))
      )}
    </div>
  );
}
