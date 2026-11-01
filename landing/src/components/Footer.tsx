import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import zillersEmblem from '../assets/emblem.png';

export const Footer: React.FC = () => {
  return (
    <footer className="border-t border-[#1E1E22] bg-[#050505] text-[#F4F4F5] pt-16 pb-12 px-6">
      {/* Call to Action Banner */}
      <div className="max-w-4xl mx-auto text-center mb-16">
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white font-mono uppercase">
          Autonomous Algorithmic Alpha.
        </h2>
        <p className="mt-3 text-sm text-[#A2A2A8] max-w-lg mx-auto">
          Systematic Intelligence. Disciplined Execution.
        </p>
        <div className="mt-8 flex justify-center">
          <a
            href="#platform"
            className="inline-flex items-center gap-2 text-sm font-medium tracking-wide bg-[#F4F4F5] text-[#050505] px-7 py-3.5 rounded-full hover:bg-white transition-all shadow-xl hover:scale-[1.02]"
          >
            <span>Explore Architecture</span>
            <ArrowUpRight className="w-4 h-4" />
          </a>
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-[#38383C] pt-12">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-12">
          {/* Brand & Corporate Provenance */}
          <div className="space-y-2">
            <div className="flex items-center gap-2.5">
              <img
                src={zillersEmblem}
                alt="ZILLERS Emblem"
                className="w-6 h-6 object-contain rounded-md"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
              <span className="font-mono text-sm font-bold tracking-widest text-white uppercase">
                ZILLERS
              </span>
            </div>
            <p className="text-xs text-[#A2A2A8] font-mono">
              Built by{' '}
              <a
                href="https://github.com/ekanth14"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white font-bold hover:text-[#D8D8DC] transition-colors"
              >
                Ekanth B S
              </a>{' '}
              · A{' '}
              <a
                href="https://ziennexus.app/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-white hover:text-[#D8D8DC] font-semibold transition-colors"
                title="Visit Zien Organisation (ziennexus.app)"
              >
                Zien Organisation
              </a>{' '}
              Company
            </p>
          </div>

          {/* Navigation Links */}
          <div className="flex flex-wrap items-center gap-6 text-xs text-[#A2A2A8] font-mono">
            <a href="#about" className="hover:text-white transition-colors">
              About
            </a>
            <a href="#platform" className="hover:text-white transition-colors">
              Platform
            </a>
            <a href="#technology" className="hover:text-white transition-colors">
              Technology
            </a>
            <a href="#vision" className="hover:text-white transition-colors">
              Vision
            </a>
            <a href="#setup" className="hover:text-white transition-colors">
              Setup
            </a>
            <a href="#faq" className="hover:text-white transition-colors">
              FAQ
            </a>
            <a href="#collaborate" className="hover:text-white transition-colors">
              Collaborate
            </a>
            <a
              href="https://github.com/ekanth14/Ziller"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition-colors inline-flex items-center gap-1"
            >
              <span>GitHub</span>
              <ArrowUpRight className="w-3 h-3" />
            </a>
          </div>
        </div>

        {/* Legal Disclaimers & Copyright */}
        <div className="pt-6 border-t border-[#222224] text-[11px] text-[#A2A2A8]/70 leading-relaxed font-mono space-y-3">
          <p>
            Regulatory Disclaimer: ZILLERS is a quantitative financial technology research venture. The software, interfaces,
            models, and metrics displayed on this website are for illustrative, research, and educational purposes only.
            ZILLERS is not an investment advisor, financial broker, or custodian, and does not solicit capital or provide investment advice.
          </p>
          <p>
            Cryptocurrency, algorithmic trading, and digital assets carry substantial financial risk of total capital loss.
            Historical backtests and simulated performance metrics do not predict future results.
          </p>
          <div className="pt-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 text-[#A2A2A8]">
            <span>© 2026 ZILLERS. Built by <a href="https://github.com/ekanth14" target="_blank" rel="noopener noreferrer" className="text-white hover:text-[#D8D8DC] font-bold transition-colors">Ekanth B S</a> · A unit of <a href="https://ziennexus.app/" target="_blank" rel="noopener noreferrer" className="text-white hover:text-[#D8D8DC] font-semibold transition-colors" title="Visit Zien Organisation (ziennexus.app)">Zien Organisation</a>. All rights reserved.</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
