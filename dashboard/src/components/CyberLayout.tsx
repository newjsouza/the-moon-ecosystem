import React, { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface CyberLayoutProps {
  children: ReactNode;
}

export function CyberLayout({ children }: CyberLayoutProps) {
  return (
    <div className="min-h-screen bg-cyber-background text-gray-200 font-sans selection:bg-cyber-accent selection:text-black">
      {/* Animated Top Header */}
      <header className="fixed top-0 w-full h-16 border-b border-cyber-accent/20 bg-cyber-base/80 backdrop-blur-md z-50 flex items-center px-6">
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-3"
        >
          <div className="w-8 h-8 rounded-full border border-cyber-accent flex items-center justify-center bg-cyber-accent/10 shadow-[0_0_10px_rgba(0,240,255,0.2)]">
            <span className="text-cyber-accent font-bold text-lg">M</span>
          </div>
          <h1 className="text-xl font-bold tracking-widest uppercase text-transparent bg-clip-text bg-gradient-to-r from-cyber-accent to-cyber-purple">
            The Moon Nexus
          </h1>
        </motion.div>
        
        <div className="ml-auto flex items-center gap-4 text-sm font-mono text-gray-400">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-cyber-success animate-pulse-fast"></div>
            <span>SYS.ONLINE</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="pt-24 pb-12 px-6 max-w-[1600px] mx-auto min-h-screen flex flex-col gap-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="flex-1 flex flex-col gap-6 h-full"
        >
          {children}
        </motion.div>
      </main>
    </div>
  );
}
