import React, { useState } from 'react';
import Navbar from './components/Navbar';
import ModuleRibbon from './components/ModuleRibbon';
import HomeDashboard from './components/HomeDashboard';
import ModuleAnalysisView from './components/ModuleAnalysisView';
import ConnectSystemModal from './components/ConnectSystemModal';
import UploadCustomStandardsModal from './components/UploadCustomStandardsModal';
import MlPipelineProgressModal from './components/MlPipelineProgressModal';
import ToastNotification from './components/ToastNotification';
import { SF_MODULES } from './data/modulesData';
import { apiService } from './services/apiService';
import './index.css';

export default function App() {
  // Modules State - dynamic to support live pipeline refreshes
  const [modulesData, setModulesData] = useState(SF_MODULES);

  // activeModuleId: restore from localStorage if available, or default to 'ec' (Employee Central)
  const [activeModuleId, setActiveModuleId] = useState(() => {
    try {
      const saved = localStorage.getItem('sf_active_module_id');
      if (saved && SF_MODULES.some((m) => m.id === saved)) {
        return saved;
      }
      if (saved === 'home') {
        return null;
      }
    } catch (e) {
      // ignore
    }
    return 'ec'; // Default to Employee Central (first module) instead of 'rcm'
  });

  // Benchmark Standards Toggle: 'standard' | 'custom'
  const [standardMode, setStandardMode] = useState('standard');
  const [customStandardsMap, setCustomStandardsMap] = useState({});
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [toast, setToast] = useState(null);

  // System Connection State
  const [isSystemConnected, setIsSystemConnected] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [connectedSystemDetails, setConnectedSystemDetails] = useState(null);

  // Architecture ML & LLM Pipeline Execution State
  const [isPipelineModalOpen, setIsPipelineModalOpen] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Deep Dive State for Auto-Hiding the Sub-Ribbon
  const [isDeepDive, setIsDeepDive] = useState(false);

  const activeModule = modulesData.find((m) => m.id === activeModuleId) || null;
  const hasCustomStandards = Object.keys(customStandardsMap).length > 0;

  const handleSelectModule = (moduleId) => {
    setActiveModuleId(moduleId);
    setIsDeepDive(false);
    try {
      localStorage.setItem('sf_active_module_id', moduleId);
    } catch (e) {
      // ignore
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleGoHome = () => {
    setActiveModuleId(null);
    setIsDeepDive(false);
    try {
      localStorage.setItem('sf_active_module_id', 'home');
    } catch (e) {
      // ignore
    }
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

  const handleTriggerRefreshPipeline = async () => {
    setIsRefreshing(true);
    setIsPipelineModalOpen(true);
    try {
      await apiService.triggerMlPipeline(activeModuleId, true);
    } catch (err) {
      console.warn('ML trigger fallback handled:', err);
    }
  };

  const handlePipelineCompleted = async () => {
    try {
      const refreshed = await apiService.getModules();
      if (refreshed && refreshed.length > 0) {
        setModulesData(refreshed);
      }
    } catch (e) {
      console.warn('Using existing modules after pipeline run:', e);
    }
    setIsRefreshing(false);
    setToast({
      id: Date.now(),
      type: 'success',
      message: 'ML Pipeline execution complete! Refreshed TreeSHAP drivers & LLM action plans.'
    });
  };

  return (
    <div className="app-container">
      {/* 1. Dark Top Header with YASH Logo & Success Factors Title */}
      <Navbar
        onGoHome={handleGoHome}
        onOpenConnectSystem={() => setIsModalOpen(true)}
        isConnected={isSystemConnected}
        onTriggerRefresh={handleTriggerRefreshPipeline}
        isRefreshing={isRefreshing}
      />

      {/* 2. Sub-Ribbon: Shown when inside a module (auto-hides in Deep Dive till hovered) */}
      {activeModule && (
        <div className={`module-ribbon-autohide-container ${isDeepDive ? 'is-autohide' : ''}`}>
          <ModuleRibbon
            modules={modulesData}
            activeModuleId={activeModuleId}
            onSelectModule={handleSelectModule}
            onGoHome={handleGoHome}
            standardMode={standardMode}
            onSelectStandardMode={handleSelectStandardMode}
            onOpenUploadModal={() => setIsUploadModalOpen(true)}
            hasCustomStandards={hasCustomStandards}
          />
        </div>
      )}

      {/* 3. Main View Area */}
      <main className="content-viewport">
        {activeModule ? (
          <ModuleAnalysisView
            module={activeModule}
            standardMode={standardMode}
            customStandardsMap={customStandardsMap}
            onGoHome={handleGoHome}
            onSelectModule={handleSelectModule}
            onDeepDiveChange={setIsDeepDive}
          />
        ) : (
          <HomeDashboard
            modules={modulesData}
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

      {/* 5. Architecture ML & LLM Pipeline Progress Modal */}
      <MlPipelineProgressModal
        isOpen={isPipelineModalOpen}
        onClose={() => {
          setIsPipelineModalOpen(false);
          setIsRefreshing(false);
        }}
        activeModuleName={activeModule?.name}
        onCompleted={handlePipelineCompleted}
      />

      {/* 6. Upload Custom Standards CSV Modal */}
      <UploadCustomStandardsModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onImport={handleImportCustomStandards}
        module={activeModule}
      />

      {/* 7. Toast Notification (bottom-right) */}
      <ToastNotification
        toast={toast}
        onClose={() => setToast(null)}
      />
    </div>
  );
}

