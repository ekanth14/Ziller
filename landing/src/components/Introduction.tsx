import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, Shield, Zap, ArrowUpRight, Github, Code2 } from 'lucide-react';
import zillersShowcaseLogo from '../assets/zillers-showcase-logo.png';
import zillersEmblem from '../assets/emblem.png';

export const Introduction: React.FC = () => {
  return (
    <section id="about" className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
        {/* Editorial Narrative */}
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8 }}
          className="lg:col-span-7 flex flex-col justify-center"
        >
          <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-4">
            The ZILLERS Mandate · About the Venture
          </span>
          <h2 className="text-3xl sm:text-5xl md:text-6xl font-semibold tracking-[-0.03em] text-metallic leading-[1.12]">
            Beyond conventional trading.
          </h2>
          <p className="mt-8 text-base md:text-xl text-[#F4F4F5] font-light leading-relaxed">
            ZILLERS is a quantitative financial technology venture under{' '}
            <a
              href="https://ziennexus.app/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-white font-semibold hover:text-[#D8D8DC] transition-colors"
              title="Visit Zien Organisation (ziennexus.app)"
            >
              Zien Organisation
            </a>
            , focused on developing accessible trading research, algorithmic automation, and intelligent cryptocurrency market analysis.
          </p>
          <p className="mt-4 text-sm md:text-base text-[#A2A2A8] font-normal leading-relaxed">
            By shifting from emotional human guesswork to deterministic algorithmic rules paired with local multi-agent deliberation,
            ZILLERS establishes a rigorous, fail-safe paradigm for digital asset strategy evaluation.
          </p>

          {/* Creator Attribution Dossier — Highlighted Author with GitHub Redirection */}
          <div className="mt-8 p-4 sm:p-5 rounded-2xl bg-[#090909] border border-[#4D4D51] shadow-2xl relative overflow-hidden group hover:border-[#D8D8DC] transition-all duration-300">
            <div className="absolute top-0 right-0 w-36 h-36 bg-white/[0.04] blur-2xl rounded-full pointer-events-none group-hover:bg-white/[0.08] transition-colors" />

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative z-10">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 text-[10px] sm:text-[11px] font-mono uppercase tracking-widest text-[#A2A2A8]">
                  <Code2 className="w-3.5 h-3.5 text-[#D8D8DC]" />
                  <span>Lead Quantitative Systems Engineer</span>
                </div>
                <div className="text-sm sm:text-base text-[#D8D8DC] font-light flex flex-wrap items-center gap-2">
                  <span>Conceived, engineered, and built by</span>
                  <a
                    href="https://github.com/ekanth14"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#151515] border border-[#4D4D51] text-[#F4F4F5] font-bold tracking-wide hover:bg-white hover:text-[#050505] hover:border-white transition-all shadow-md group/author"
                    title="View Ekanth B S on GitHub"
                  >
                    <span className="text-white group-hover/author:text-[#050505] font-bold">
                      Ekanth B S
                    </span>
                    <Github className="w-3.5 h-3.5 opacity-80 group-hover/author:opacity-100 transition-opacity" />
                    <ArrowUpRight className="w-3.5 h-3.5 opacity-60 group-hover/author:opacity-100 group-hover/author:translate-x-0.5 group-hover/author:-translate-y-0.5 transition-transform" />
                  </a>
                </div>
              </div>

              <a
                href="https://github.com/ekanth14"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-mono text-[#D8D8DC] bg-[#151515] border border-[#38383C] hover:border-[#F4F4F5] hover:text-white transition-all self-start sm:self-center shrink-0"
              >
                <span>github.com/ekanth14</span>
                <ArrowUpRight className="w-3 h-3" />
              </a>
            </div>
          </div>

          <div className="mt-10 grid grid-cols-2 gap-6 pt-6 border-t border-[#38383C]">
            <div>
              <div className="text-2xl font-mono font-bold text-white tracking-tight">0.00%</div>
              <div className="text-xs text-[#A2A2A8] mt-1 font-mono uppercase">Subscription Cost</div>
            </div>
            <div>
              <div className="text-2xl font-mono font-bold text-white tracking-tight">100%</div>
              <div className="text-xs text-[#A2A2A8] mt-1 font-mono uppercase">Reproducible Code</div>
            </div>
          </div>
        </motion.div>

        {/* Technical Blueprint Visual (With Brand Logo Showcase) */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.8 }}
          className="lg:col-span-5 relative"
        >
          <div className="relative rounded-3xl border border-[#4D4D51] bg-[#151515] p-6 shadow-2xl overflow-hidden">
            {/* Corner Decorative Crosshairs */}
            <div className="absolute top-3 left-3 text-[#A2A2A8] font-mono text-[9px]">+</div>
            <div className="absolute top-3 right-3 text-[#A2A2A8] font-mono text-[9px]">+</div>
            <div className="absolute bottom-3 left-3 text-[#A2A2A8] font-mono text-[9px]">+</div>
            <div className="absolute bottom-3 right-3 text-[#A2A2A8] font-mono text-[9px]">+</div>

            {/* Official Metallic Logo Showcase */}
            <div className="mb-6 p-6 rounded-2xl bg-[#090909] border border-[#38383C] flex flex-col items-center justify-center text-center relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-b from-white/[0.04] to-transparent pointer-events-none" />
              <img
                src={zillersShowcaseLogo}
                alt="ZILLERS Official Logo"
                className="w-52 sm:w-60 object-contain filter drop-shadow-[0_8px_30px_rgba(255,255,255,0.08)] relative z-10 transition-transform duration-300 group-hover:scale-105"
                onError={(e) => {
                  (e.target as HTMLImageElement).src = zillersEmblem;
                }}
              />
              <span className="mt-3 font-mono text-[10px] tracking-widest text-[#A2A2A8] uppercase relative z-10">
                Institutional Quant Ecosystem
              </span>
            </div>

            <div className="font-mono text-[10px] tracking-wider text-[#A2A2A8] mb-4 pb-3 border-b border-[#38383C] flex items-center justify-between">
              <span>SYSTEM DISCIPLINE // PILLARS</span>
              <span className="text-[#D8D8DC]">STANDALONE ENCLAVE</span>
            </div>

            <div className="space-y-4">
              <div className="p-3.5 rounded-xl bg-[#222224] border border-[#38383C] flex items-start gap-3">
                <div className="p-2 rounded-lg bg-[#151515] text-[#D8D8DC]">
                  <Zap className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-[#F4F4F5] uppercase tracking-wide">Deterministic Execution</h4>
                  <p className="text-[11px] text-[#A2A2A8] mt-0.5 leading-snug">
                    Zero latency emotional drift. Execution logic enforces mathematically verified entry and exit conditions.
                  </p>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-[#222224] border border-[#38383C] flex items-start gap-3">
                <div className="p-2 rounded-lg bg-[#151515] text-[#D8D8DC]">
                  <Terminal className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-[#F4F4F5] uppercase tracking-wide">Autonomous Deliberation</h4>
                  <p className="text-[11px] text-[#A2A2A8] mt-0.5 leading-snug">
                    Tier 2 local LLM reasoning evaluates macro market regimes and liquidity stress before granting proposal consensus.
                  </p>
                </div>
              </div>

              <div className="p-3.5 rounded-xl bg-[#222224] border border-[#38383C] flex items-start gap-3">
                <div className="p-2 rounded-lg bg-[#151515] text-[#D8D8DC]">
                  <Shield className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="text-xs font-semibold text-[#F4F4F5] uppercase tracking-wide">Failsafe Risk Governance</h4>
                  <p className="text-[11px] text-[#A2A2A8] mt-0.5 leading-snug">
                    Strict daily loss bounds, Deflated Sharpe Ratio thresholds, and instant dual-action emergency kill switch protection.
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-3 border-t border-[#38383C] flex justify-between items-center text-[10px] font-mono text-[#A2A2A8]">
              <a
                href="https://ziennexus.app/"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-white transition-colors inline-flex items-center gap-1"
                title="Visit Zien Organisation (ziennexus.app)"
              >
                <span>ZIEN ORG RESEARCH LAB</span>
                <span className="text-[9px]">↗</span>
              </a>
              <span className="text-[#D8D8DC]">PRODUCTION VERIFIED</span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
