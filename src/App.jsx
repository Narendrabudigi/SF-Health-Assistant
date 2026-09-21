import React, { useState } from 'react';
import Navbar from './components/Navbar';
import ModuleRibbon from './components/ModuleRibbon';
import HomeDashboard from './components/HomeDashboard';
import ModuleAnalysisView from './components/ModuleAnalysisView';
import ConnectSystemModal from './components/ConnectSystemModal';
import UploadCustomStandardsModal from './components/UploadCustomStandardsModal';
import ToastNotification from './components/ToastNotification';
import { SF_MODULES } from './data/modulesData';
import './index.css';

export default function App() {
  // activeModuleId: null indicates Overview/Home, string ID indicates module analysis view
  const [activeModuleId, setActiveModuleId] = useState(null);
  
  // Benchmark Standards Toggle: 'standard' | 'custom'
  const [standardMode, setStandardMode] = useState('standard');
  const [customStandardsMap, setCustomStandardsMap] = useState({});
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [toast, setToast] = useState(null);

  // System Connection State
  const [isSystemConnected, setIsSystemConnected] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [connectedSystemDetails, setConnectedSystemDetails] = useState(null);

  const activeModule = SF_MODULES.find((m) => m.id === activeModuleId) || null;
  const hasCustomStandards = Object.keys(customStandardsMap).length > 0;

  const handleSelectModule = (moduleId) => {
    setActiveModuleId(moduleId);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleGoHome = () => {
    setActiveModuleId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectStandardMode = (mode) => {
    if (mode === 'custom') {
      if (!hasCustomStandards) {
        setToast({
          id: Date.now(),
          type: 'warning',
          message: 'No custom standards uploaded yet. Please use "Upload Standards" button to import a CSV file first.'
        });
        return;
      }
      setStandardMode('custom');
      return;
    }
    setStandardMode('standard');
  };

  const handleImportCustomStandards = (newStandardsMap) => {
    setCustomStandardsMap((prev) => ({ ...prev, ...newStandardsMap }));
    setStandardMode('custom');
    setToast({
      id: Date.now(),
      type: 'success',
      message: `Custom standards successfully imported (${Object.keys(newStandardsMap).length} metrics updated).`
    });
  };

  const handleConnectSuccess = (details) => {
    setIsSystemConnected(true);
    setConnectedSystemDetails(details);
  };

  const handleDisconnect = () => {
    setIsSystemConnected(false);
    setConnectedSystemDetails(null);
  };

  return (
    <div className="app-container">
      {/* 1. Dark Top Header with YASH Logo & Success Factors Title */}
      <Navbar 
        onGoHome={handleGoHome} 
        onOpenConnectSystem={() => setIsModalOpen(true)}
        isConnected={isSystemConnected}
      />

      {/* 2. Sub-Ribbon: Shown when inside a module, with Standard/Custom toggle & Upload trigger */}
      {activeModule && (
        <ModuleRibbon 
          modules={SF_MODULES} 
          activeModuleId={activeModuleId} 
          onSelectModule={handleSelectModule} 
          onGoHome={handleGoHome}
          standardMode={standardMode}
          onSelectStandardMode={handleSelectStandardMode}
          onOpenUploadModal={() => setIsUploadModalOpen(true)}
          hasCustomStandards={hasCustomStandards}
        />
      )}

      {/* 3. Main View Area */}
      <main className="content-viewport">
        {activeModule ? (
          <ModuleAnalysisView 
            module={activeModule} 
            standardMode={standardMode} 
            customStandardsMap={customStandardsMap}
          />
        ) : (
          <HomeDashboard 
            modules={SF_MODULES} 
            onSelectModule={handleSelectModule} 
          />
        )}
      </main>

      {/* 4. Connect SAP SuccessFactors System Modal */}
      <ConnectSystemModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        isConnected={isSystemConnected}
        onConnect={handleConnectSuccess}
        onDisconnect={handleDisconnect}
      />

      {/* 5. Upload Custom Standards CSV Modal */}
      <UploadCustomStandardsModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onImport={handleImportCustomStandards}
        module={activeModule}
      />

      {/* 6. Toast Notification (bottom-right) */}
      <ToastNotification 
        toast={toast} 
        onClose={() => setToast(null)} 
      />
    </div>
  );
}

