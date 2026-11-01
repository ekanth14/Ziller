import React, { useState } from 'react';
import { ChevronDown, HelpCircle, ArrowUpRight } from 'lucide-react';

interface FAQItem {
  question: string;
  answer: React.ReactNode;
}

const FAQS: FAQItem[] = [
  {
    question: 'What is ZILLERS?',
    answer: (
      <p>
        ZILLERS is a precision-engineered quantitative cryptocurrency execution platform and deliberative AI architecture.
        It shifts trading away from discretionary emotional guesswork into mathematically validated, deterministic algorithmic
        rulebooks, Smart Money Concepts (SMC), Fair Value Gaps (FVG), and sub-20ms Smart Order Routing (SOR).
      </p>
    ),
  },
  {
    question: 'Who created ZILLERS and what is its relation to Zien Organisation?',
    answer: (
      <p>
        ZILLERS was conceived, engineered, and built by{' '}
        <a
          href="https://github.com/ekanth14"
          target="_blank"
          rel="noopener noreferrer"
          className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
        >
          Ekanth B S
        </a>
        . It operates as a dedicated quantitative financial technology initiative under parent venture{' '}
        <a
          href="https://ziennexus.app/"
          target="_blank"
          rel="noopener noreferrer"
          className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
        >
          Zien Organisation
        </a>
        .
      </p>
    ),
  },
  {
    question: 'Is ZILLERS free or does it require a subscription fee?',
    answer: (
      <p>
        ZILLERS is 100% free with a $0.00 subscription cost. The platform is committed to open, reproducible quantitative
        science. All core code, execution models, and documentation are publicly available on GitHub at{' '}
        <a
          href="https://github.com/ekanth14/Ziller"
          target="_blank"
          rel="noopener noreferrer"
          className="font-bold text-white hover:text-[#D8D8DC] transition-colors"
        >
          github.com/ekanth14/Ziller
        </a>
        .
      </p>
    ),
  },
  {
    question: 'How does ZILLERS validate quantitative trading strategies?',
    answer: (
      <p>
        ZILLERS controls for data-snooping bias across multiple trial iterations using the Deflated Sharpe Ratio (DSR 0.98),
        walk-forward optimization, and combinatorial cross-validation across volatile digital asset market regimes.
      </p>
    ),
  },
  {
    question: 'What is Laya AI and how does it make trade decisions?',
    answer: (
      <p>
        Laya AI is an offline, local multi-agent deliberation committee powered by lightweight local LLMs. It analyzes
        quantitative trade candidate proposals, tests counter-theses, and enforces strict JSON schema validation before
        submitting any order to the deterministic 5-gate pre-trade risk engine.
      </p>
    ),
  },
  {
    question: 'How can researchers and developers collaborate with ZILLERS?',
    answer: (
      <p>
        Researchers, quantitative analysts, and infrastructure engineers can submit collaboration proposals directly via the{' '}
        <a href="#collaborate" className="font-bold text-white hover:text-[#D8D8DC] transition-colors">
          Collaborate Section
        </a>{' '}
        or at{' '}
        <a href="/collaborate" className="font-bold text-white hover:text-[#D8D8DC] transition-colors">
          /collaborate
        </a>
        . Submitted proposals are reviewed at the passcode-protected Proposals Desk.
      </p>
    ),
  },
];

export const FAQ: React.FC = () => {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggle = (idx: number) => {
    setOpenIndex(openIndex === idx ? null : idx);
  };

  return (
    <section id="faq" className="py-24 border-t border-[#1E1E22] bg-[#050505] relative">
      <div className="max-w-4xl mx-auto px-6">
        {/* Section Header */}
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#151518] border border-[#27272A] text-xs font-mono text-[#A2A2A8] uppercase tracking-wider mb-4">
            <HelpCircle className="w-3.5 h-3.5 text-amber-300" />
            <span>Knowledge Base · AEO & FAQs</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight text-white mb-4">
            Frequently Asked Questions
          </h2>
          <p className="text-sm sm:text-base text-[#A2A2A8] max-w-xl mx-auto leading-relaxed">
            Direct, factual specifications regarding ZILLERS architecture, venture provenance, technology stack, and licensing.
          </p>
        </div>

        {/* Semantic FAQ Accordion List */}
        <div className="space-y-3" itemScope itemType="https://schema.org/FAQPage">
          {FAQS.map((faq, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                itemScope
                itemProp="mainEntity"
                itemType="https://schema.org/Question"
                className="rounded-2xl bg-[#0B0B0D] border border-[#222226] hover:border-[#38383C] transition-colors overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => toggle(idx)}
                  className="w-full p-5 sm:p-6 text-left flex items-center justify-between gap-4 focus:outline-none"
                  aria-expanded={isOpen}
                >
                  <span itemProp="name" className="text-sm sm:text-base font-semibold text-white">
                    {faq.question}
                  </span>
                  <div
                    className={`p-1.5 rounded-lg bg-[#151518] border border-[#27272A] text-[#A2A2A8] transition-transform duration-200 shrink-0 ${
                      isOpen ? 'rotate-180 text-white' : ''
                    }`}
                  >
                    <ChevronDown className="w-4 h-4" />
                  </div>
                </button>

                {isOpen && (
                  <div
                    itemScope
                    itemProp="acceptedAnswer"
                    itemType="https://schema.org/Answer"
                    className="px-5 pb-5 sm:px-6 sm:pb-6 text-xs sm:text-sm text-[#A2A2A8] leading-relaxed border-t border-[#18181B] pt-4"
                  >
                    <div itemProp="text">{faq.answer}</div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* LLM & AI Engine Direct Citation Link */}
        <div className="mt-12 p-4 rounded-2xl bg-[#0D0D10] border border-[#222226] flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono text-[#888]">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span>Generative Engine Optimization (GEO) & Machine-Readable Spec</span>
          </div>
          <div className="flex items-center gap-4">
            <a
              href="/llms.txt"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#D8D8DC] hover:text-white inline-flex items-center gap-1 transition-colors"
            >
              <span>/llms.txt</span>
              <ArrowUpRight className="w-3 h-3" />
            </a>
            <a
              href="/sitemap.xml"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#D8D8DC] hover:text-white inline-flex items-center gap-1 transition-colors"
            >
              <span>/sitemap.xml</span>
              <ArrowUpRight className="w-3 h-3" />
            </a>
          </div>
        </div>
      </div>
    </section>
  );
};
