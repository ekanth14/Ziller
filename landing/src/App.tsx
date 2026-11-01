import React from 'react';
import { Navigation } from './components/Navigation';
import { Hero } from './components/Hero';
import { ProductShowcase } from './components/ProductShowcase';
import { Introduction } from './components/Introduction';
import { CoreCapabilities } from './components/CoreCapabilities';
import { ArchitecturePipeline } from './components/ArchitecturePipeline';
import { LayaAISection } from './components/LayaAISection';
import { RiskPhilosophy } from './components/RiskPhilosophy';
import { FreePhilosophy } from './components/FreePhilosophy';
import { ZienOrganisation } from './components/ZienOrganisation';
import { Footer } from './components/Footer';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-[#050505] text-[#F4F4F5] selection:bg-[#38383C] selection:text-white relative overflow-x-hidden font-sans">
      {/* Smoked Glass Top Navigation */}
      <Navigation />

      {/* Main Flow */}
      <main>
        {/* 1. Hero Viewport Stage */}
        <Hero />

        {/* 2. Institutional Product Showcase */}
        <ProductShowcase />

        {/* 3. Introducing ZILLERS */}
        <Introduction />

        {/* 4. Core Capabilities */}
        <CoreCapabilities />

        {/* 5. Technology Architecture Pipeline */}
        <ArchitecturePipeline />

        {/* 6. Dedicated Laya AI Section */}
        <LayaAISection />

        {/* 7. Risk and Research Philosophy */}
        <RiskPhilosophy />

        {/* 8. Free Software Philosophy */}
        <FreePhilosophy />

        {/* 9. Zien Organisation Parent Showcase */}
        <ZienOrganisation />
      </main>

      {/* 10. Closing Section and Minimalist Footer */}
      <Footer />
    </div>
  );
};

export default App;
