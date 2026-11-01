import React from 'react';
import { motion } from 'framer-motion';
import zillersEmblem from '../assets/emblem.png';
import zienEmblem from '../assets/zien-emblem.png';

export const ZienOrganisation: React.FC = () => {
  return (
    <section className="relative py-32 px-4 md:px-8 max-w-7xl mx-auto border-t border-[#38383C]/40 bg-[#050505]">
      <div className="max-w-3xl mx-auto flex flex-col items-center text-center">
        {/* Generous Surrounding Whitespace with Centered Dual Crest Alliance */}
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.8 }}
          className="relative mb-12 flex items-center justify-center gap-4 sm:gap-6"
        >
          {/* Subtle Ambient Halo */}
          <div className="absolute inset-0 w-72 h-36 -top-4 left-1/2 -translate-x-1/2 bg-white/[0.04] blur-[50px] rounded-full pointer-events-none" />

          {/* Official Metallic ZILLERS Logo Badge */}
          <div className="relative z-10 w-24 h-24 sm:w-28 sm:h-28 rounded-3xl bg-[#090909] border border-[#4D4D51] flex flex-col items-center justify-center p-3 shadow-2xl hover:border-white transition-colors">
            <img
              src={zillersEmblem}
              alt="ZILLERS Official Logo"
              className="w-full h-full object-contain filter drop-shadow-[0_4px_16px_rgba(255,255,255,0.15)]"
            />
          </div>

          <div className="relative z-10 flex flex-col items-center justify-center text-[#4D4D51] font-mono text-xs">
            <div className="w-[1px] h-6 sm:h-8 bg-[#38383C]" />
            <span className="py-1 text-[9px] sm:text-[10px] text-[#A2A2A8] font-bold tracking-widest">UNDER</span>
            <div className="w-[1px] h-6 sm:h-8 bg-[#38383C]" />
          </div>

          {/* Parent Zien Crest */}
          <div className="relative z-10 w-24 h-24 sm:w-28 sm:h-28 rounded-3xl bg-[#090909] border border-[#E5C07B]/30 flex flex-col items-center justify-center p-3.5 sm:p-4 shadow-[0_0_40px_rgba(229,192,123,0.12)]">
            <img
              src={zienEmblem}
              alt="Zien Organisation"
              className="w-full h-full object-contain filter drop-shadow-[0_4px_12px_rgba(229,192,123,0.3)]"
            />
          </div>
        </motion.div>

        {/* Section Heading */}
        <motion.span
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="font-mono text-[10px] md:text-xs tracking-[0.25em] text-[#A2A2A8] uppercase mb-4"
        >
          Parent Entity Provenance
        </motion.span>

        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.1 }}
          className="text-3xl sm:text-5xl font-semibold tracking-tight text-metallic leading-[1.15]"
        >
          An innovation under Zien Organisation.
        </motion.h2>

        {/* Supporting Paragraph */}
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8, delay: 0.2 }}
          className="mt-6 text-sm sm:text-base md:text-lg text-[#A2A2A8] font-normal leading-relaxed max-w-2xl"
        >
          ZILLERS represents Zien Organisation's pursuit of research-driven,
          accessible financial technology and intelligent quantitative software.
        </motion.p>

        {/* Corporate Metadata Pill */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6, delay: 0.3 }}
          className="mt-8 inline-flex items-center gap-3 px-4 py-2 rounded-full border border-[#38383C] bg-[#151515] font-mono text-xs text-[#D8D8DC]"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#E5C07B]" />
          <span>INDUSTRY: FINTECH & QUANTITATIVE SYSTEMS</span>
        </motion.div>
      </div>
    </section>
  );
};
