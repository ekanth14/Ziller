import React from 'react';
import { motion } from 'framer-motion';
import { Terminal, Shield, Zap } from 'lucide-react';

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
            The Zillers Mandate
          </span>
          <h2 className="text-3xl sm:text-5xl md:text-6xl font-semibold tracking-[-0.03em] text-metallic leading-[1.12]">
            Beyond conventional trading.
          </h2>
          <p className="mt-8 text-base md:text-xl text-[#F4F4F5] font-light leading-relaxed">
            ZILLERS is a quantitative financial technology venture under Zien Organisation,
            focused on developing accessible trading research, algorithmic automation, and intelligent cryptocurrency market analysis.
          </p>
          <p className="mt-4 text-sm md:text-base text-[#A2A2A8] font-normal leading-relaxed">
            By shifting from emotional human guesswork to deterministic algorithmic rules paired with local multi-agent deliberation,
            ZILLERS establishes a rigorous, fail-safe paradigm for digital asset strategy evaluation.
          </p>

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

        {/* Technical Blueprint Visual (Monochrome Institutional Graphic) */}
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
              <span>ZIEN ORG RESEARCH LAB</span>
              <span className="text-[#D8D8DC]">STAGE: V4.2</span>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};
