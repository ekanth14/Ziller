import React from 'react';
import { motion } from 'framer-motion';
import { Check, Info } from 'lucide-react';

export const FreePhilosophy: React.FC = () => {
  return (
    <section className="relative py-28 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40">
      <div className="relative rounded-[36px] border border-[#38383C] bg-[#090909] p-8 md:p-16 text-center overflow-hidden technical-grid shadow-2xl">
        {/* Subtle Ambient Radial Lighting */}
        <div className="absolute top-0 inset-x-0 h-96 bg-gradient-to-b from-[#D8D8DC]/5 via-transparent to-transparent pointer-events-none" />

        <div className="relative z-10 max-w-3xl mx-auto flex flex-col items-center">
          {/* Eyebrow */}
          <span className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-4">
            Access Without Barriers
          </span>

          {/* Large Headline */}
          <h2 className="text-3xl sm:text-5xl md:text-6xl font-semibold tracking-tight text-metallic leading-[1.12]">
            Intelligent software.<br />
            No subscription required.
          </h2>

          {/* Supporting Text */}
          <p className="mt-6 text-sm sm:text-base md:text-lg text-[#A2A2A8] leading-relaxed max-w-2xl">
            ZILLERS is committed to making quantitative trading technology accessible without software subscription or licensing fees.
          </p>

          {/* Prominent Secondary Metallic Typography */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="mt-10 py-6 px-10 rounded-3xl border border-[#4D4D51] bg-[#151515] shadow-xl inline-block"
          >
            <div className="text-3xl sm:text-5xl md:text-6xl font-mono font-bold tracking-tight text-metallic">
              ₹0 — SOFTWARE FEES
            </div>
            <div className="mt-2 text-xs font-mono text-[#A2A2A8] uppercase tracking-widest">
              Zero License Fees · Zero Tiered Upgrades · Zero Vendor Lock-in
            </div>
          </motion.div>

          {/* Transparent Notice */}
          <div className="mt-8 flex items-center gap-2 text-xs text-[#A2A2A8]/70 font-mono">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>
              External exchange transaction fees, blockchain gas costs, and market trading risks remain operator responsibilities.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
};
