import React from 'react';
import { motion } from 'framer-motion';
import { Network, Layers, GitMerge, FileText } from 'lucide-react';

export const LayaAISection: React.FC = () => {
  return (
    <section className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40 overflow-hidden">
      {/* Soft Ambient Silver Halo */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-white/[0.02] blur-[140px] rounded-full pointer-events-none" />

      <div className="relative z-10 grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        {/* Abstract Connected Nodes / Particle Visualization */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8 }}
          className="lg:col-span-6 relative flex justify-center"
        >
          <div className="w-full max-w-md aspect-square rounded-3xl border border-[#4D4D51] bg-[#090909] p-8 flex flex-col justify-between shadow-2xl relative overflow-hidden technical-grid">
            <div className="flex items-center justify-between text-[10px] font-mono text-[#A2A2A8]">
              <span>LAYA MULTI-AGENT TOPOLOGY</span>
              <span className="text-[#D8D8DC]">LOCAL RUNTIME: GEMMA 4</span>
            </div>

            {/* Central Node Lattice Graphic */}
            <div className="relative my-auto flex items-center justify-center">
              {/* Outer Ring */}
              <div className="w-56 h-56 rounded-full border border-dashed border-[#38383C] flex items-center justify-center animate-spin-slow">
                <div className="w-40 h-40 rounded-full border border-[#4D4D51] flex items-center justify-center">
                  {/* Core Deliberation Hub */}
                  <div className="w-20 h-20 rounded-2xl bg-[#151515] border border-white/20 flex flex-col items-center justify-center text-center p-2 shadow-xl">
                    <span className="font-mono text-[9px] text-[#A2A2A8] uppercase">CORE</span>
                    <span className="font-mono text-xs font-bold text-white">LAYA</span>
                  </div>
                </div>
              </div>

              {/* Satellite Agent Nodes */}
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-2.5 py-1 rounded-md bg-[#222224] border border-[#4D4D51] text-[9px] font-mono text-[#D8D8DC]">
                Technical Analyst
              </div>
              <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 px-2.5 py-1 rounded-md bg-[#222224] border border-[#4D4D51] text-[9px] font-mono text-[#D8D8DC]">
                Liquidity Risk
              </div>
              <div className="absolute top-1/2 -left-6 -translate-y-1/2 px-2.5 py-1 rounded-md bg-[#222224] border border-[#4D4D51] text-[9px] font-mono text-[#D8D8DC]">
                Macro Regime
              </div>
              <div className="absolute top-1/2 -right-6 -translate-y-1/2 px-2.5 py-1 rounded-md bg-[#222224] border border-[#4D4D51] text-[9px] font-mono text-[#D8D8DC]">
                Thesis Auditor
              </div>
            </div>

            <div className="pt-4 border-t border-[#38383C] flex justify-between items-center text-[10px] font-mono text-[#A2A2A8]">
              <span>FAIL-CLOSED CONTRACT</span>
              <span className="text-[#D8D8DC]">ZERO STUBBED OUTPUTS</span>
            </div>
          </div>
        </motion.div>

        {/* Narrative & Details */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8 }}
          className="lg:col-span-6 flex flex-col justify-center"
        >
          <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-4">
            Deliberative Intelligence
          </span>
          <h2 className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic leading-[1.12]">
            Meet Laya. A different dimension of intelligence.
          </h2>
          <p className="mt-6 text-sm md:text-base text-[#A2A2A8] leading-relaxed">
            Rather than relying on ungrounded generative predictions or opaque black-box models,
            Laya proposes a local multi-agent reasoning architecture designed exclusively to debate and challenge trading proposals.
          </p>

          <div className="mt-8 space-y-4">
            <div className="flex items-start gap-4 p-4 rounded-2xl bg-[#151515] border border-[#38383C]">
              <div className="p-2 rounded-xl bg-[#222224] text-[#D8D8DC] shrink-0">
                <Network className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-[#F4F4F5]">Structured Multi-Agent Debate</h4>
                <p className="text-xs text-[#A2A2A8] mt-1 leading-relaxed">
                  Multiple simulated analytical agents—representing technical momentum, liquidity stress, and macro volatility—must reach consensus before any signal advances.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-2xl bg-[#151515] border border-[#38383C]">
              <div className="p-2 rounded-xl bg-[#222224] text-[#D8D8DC] shrink-0">
                <GitMerge className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-[#F4F4F5]">Local Inference Independence</h4>
                <p className="text-xs text-[#A2A2A8] mt-1 leading-relaxed">
                  Engineered to operate on self-hosted local checkpoints (such as Gemma 4 via Ollama). Zero trade information or prompt context ever leaves the local machine.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-4 p-4 rounded-2xl bg-[#151515] border border-[#38383C]">
              <div className="p-2 rounded-xl bg-[#222224] text-[#D8D8DC] shrink-0">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <h4 className="text-sm font-semibold text-[#F4F4F5]">Strict Explainability & Auditability</h4>
                <p className="text-xs text-[#A2A2A8] mt-1 leading-relaxed">
                  Every decision outputs a complete rationale thesis, debate transcripts, and risk scores. If Laya cannot meet the execution timeout, it explicitly reports timeout rather than faking assent.
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
