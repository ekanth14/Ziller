import React, { useState, useEffect } from 'react';
import { Menu, X, ArrowUpRight } from 'lucide-react';

export const Navigation: React.FC = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 40);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { label: 'About', href: '#about' },
    { label: 'Platform', href: '#platform' },
    { label: 'Technology', href: '#technology' },
    { label: 'Vision', href: '#vision' },
    { label: 'Collaborate', href: '#collaborate' },
  ];

  return (
    <header className="fixed top-5 inset-x-0 z-50 flex justify-center px-4 pointer-events-none">
      <nav
        className={`pointer-events-auto flex items-center justify-between gap-6 px-4 py-2.5 rounded-full border transition-all duration-300 ${
          scrolled
            ? 'bg-[#151515]/90 border-[#4D4D51] shadow-2xl backdrop-blur-xl shadow-black/80'
            : 'bg-[#151515]/70 border-[#38383C] backdrop-blur-md'
        } max-w-fit w-full`}
        aria-label="Main Navigation"
      >
        {/* Brand */}
        <a href="#" className="flex items-center gap-2.5 pl-2 group">
          <img
            src="./assets/emblem.png"
            alt="Zillers"
            className="w-5 h-5 object-contain opacity-90 group-hover:opacity-100 transition-opacity"
            onError={(e) => {
              (e.target as HTMLElement).style.display = 'none';
            }}
          />
          <span className="font-mono text-xs font-semibold tracking-widest text-[#F4F4F5] uppercase">
            ZILLERS
          </span>
        </a>

        {/* Desktop Nav Links */}
        <div className="hidden md:flex items-center gap-6 text-[13px] text-[#A2A2A8]">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="hover:text-[#F4F4F5] transition-colors duration-150"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Action Button */}
        <div className="flex items-center gap-2">
          <a
            href="#platform"
            className="inline-flex items-center gap-1 text-[12px] font-medium tracking-wide bg-[#F4F4F5] text-[#050505] px-3.5 py-1.5 rounded-full hover:bg-white transition-all shadow-sm hover:scale-[1.02]"
          >
            <span>Explore</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </a>

          {/* Mobile menu trigger */}
          <button
            type="button"
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-1 text-[#A2A2A8] hover:text-[#F4F4F5]"
            aria-label="Toggle Menu"
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </nav>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="pointer-events-auto fixed top-20 inset-x-4 max-w-sm mx-auto bg-[#151515] border border-[#4D4D51] rounded-2xl p-4 shadow-2xl backdrop-blur-2xl md:hidden flex flex-col gap-3">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="text-sm text-[#A2A2A8] hover:text-white py-1.5 px-3 rounded-lg hover:bg-[#222224] transition-colors"
            >
              {link.label}
            </a>
          ))}
          <div className="pt-2 border-t border-[#38383C]">
            <a
              href="#platform"
              onClick={() => setMobileOpen(false)}
              className="block w-full text-center text-xs font-semibold bg-[#F4F4F5] text-[#050505] py-2 rounded-xl"
            >
              Explore ZILLERS
            </a>
          </div>
        </div>
      )}
    </header>
  );
};
