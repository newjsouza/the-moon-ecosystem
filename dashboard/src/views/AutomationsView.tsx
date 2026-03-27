import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ServerCog, Activity, AlertOctagon } from 'lucide-react';
import clsx from 'clsx';

interface TaskData {
  id: string;
  name: string;
  status: string;
  type: string;
  details: string;
}

export function AutomationsView() {
  const [tasks, setTasks] = useState<TaskData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/tasks');
        const data = await res.json();
        if (data.tasks) setTasks(data.tasks);
      } catch (err) {
        console.error('Failed to fetch tasks:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">
      <div className="lg:col-span-12 glass-panel p-6 overflow-hidden flex flex-col gap-6">
        <h2 className="text-xl font-mono text-white border-b border-white/20 pb-4 flex justify-between items-center">
          <span className="flex items-center gap-3">
            <ServerCog className="w-6 h-6 text-cyber-purple" />
            [ DAEMONS & AUTOMATIONS CORE ]
          </span>
          <span className="text-xs text-cyber-purple/80 animate-pulse-slow">ACTIVE QUEUES</span>
        </h2>

        <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 flex flex-col gap-4">
          {loading && tasks.length === 0 ? (
            <div className="text-cyber-purple animate-pulse font-mono text-sm">FETCHING DAEMONS...</div>
          ) : (
            tasks.map((task, idx) => (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.1 }}
                className={clsx(
                  "p-5 rounded-lg border flex flex-col md:flex-row md:items-center justify-between gap-4 font-mono group transition-colors",
                  task.status === 'running' ? "bg-black/40 border-cyber-purple/30 hover:bg-cyber-purple/5" : "bg-red-900/10 border-red-500/30"
                )}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-3">
                    <span className="text-lg font-bold text-white tracking-widest">{task.name}</span>
                    <span className="text-[10px] uppercase tracking-widest border border-white/20 px-2 py-0.5 rounded text-gray-400">
                      TYPE: {task.type}
                    </span>
                  </div>
                  <div className="text-sm text-gray-400">
                    {task.details}
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className={clsx(
                    "flex flex-col items-end border-r border-white/10 pr-4",
                    task.status === 'running' ? "text-cyber-purple" : "text-red-400"
                  )}>
                    <span className="text-[10px] tracking-widest uppercase">State</span>
                    <span className="font-bold flex items-center gap-1">
                      {task.status === 'running' ? <Activity className="w-4 h-4" /> : <AlertOctagon className="w-4 h-4" />}
                      {task.status.toUpperCase()}
                    </span>
                  </div>
                  <button className="px-4 py-3 bg-white/5 hover:bg-white/10 rounded border border-white/10 text-xs tracking-widest text-white transition-colors h-10 flex items-center justify-center">
                    DETAILS
                  </button>
                </div>
              </motion.div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
