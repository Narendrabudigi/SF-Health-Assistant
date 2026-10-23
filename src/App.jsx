import React, { useState, useEffect } from 'react';
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
  // Modules State - dynamic to support live pipeline refreshes & Supabase data
  const [modulesData, setModulesData] = useState(SF_MODULES);
  const [dataRefreshVersion, setDataRefreshVersion] = useState(0);

  // Backend & Supabase Live Telemetry Status
  const [backendStatus, setBackendStatus] = useState({
    isConnected: false,
    supabaseConnected: false,
    bucketFiles: 0,
    bucketName: 'ml-insights',
    folder: 'insights'
  });

  // Fetch live modules and verify backend + Supabase storage connection on mount
  useEffect(() => {
    let isMounted = true;
    async function loadLiveBackendData() {
      const [statusResult, modulesResult, standardsResult] = await Promise.allSettled([
        apiService.checkHealthWithSupabase(),
        apiService.getModules(),
        apiService.getCustomStandards()
      ]);

      if (!isMounted) return;

      if (statusResult.status === 'fulfilled') {
        setBackendStatus(statusResult.value);
      } else {
        console.warn('Backend health check failed:', statusResult.reason);
      }

      if (modulesResult.status === 'fulfilled' && modulesResult.value?.length > 0) {
        setModulesData(modulesResult.value);
      } else if (modulesResult.status === 'rejected') {
        console.warn('Backend module fetch failed, using default cached modules:', modulesResult.reason);
      }
      if (standardsResult.status === 'fulfilled' && standardsResult.value?.exists) {
        setCustomStandardsMap(standardsResult.value.standardsMap || {});
      } else if (standardsResult.status === 'rejected') {
        console.warn('Custom standards could not be loaded from Supabase:', standardsResult.reason);
      }
    }
    loadLiveBackendData();
    return () => { isMounted = false; };
  }, []);

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

  const handleSelectStandardMode = async (mode) => {
    if (mode === 'custom') {
      if (!hasCustomStandards) {
        setToast({
          id: Date.now(),
          type: 'warning',
          message: 'No custom standards workbook is available in Supabase. Upload the .xlsx workbook first.'
        });
        return;
      }
    }
    setStandardMode(mode);
    try {
      const refreshed = await apiService.getModules(false, mode === 'custom' ? 'custom' : 'industry');
      if (refreshed?.length) setModulesData(refreshed);
    } catch (error) {
      console.warn(`Could not load ${mode} module data:`, error);
    }
  };

  const handleImportCustomStandards = async (newStandardsMap) => {
    setCustomStandardsMap(newStandardsMap);
    setStandardMode('custom');
    try {
      const refreshed = await apiService.getModules(true, 'custom');
      if (refreshed?.length) setModulesData(refreshed);
    } catch (error) {
      console.warn('Custom workbook was uploaded, but custom metric results could not be loaded:', error);
    }
    setToast({
      id: Date.now(),
      type: 'success',
      message: `Custom standards workbook replaced in Supabase (${Object.keys(newStandardsMap).length} metrics). Refresh to run the custom ML and LLM pipeline.`
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
  };

  const handlePipelineCompleted = async () => {
    try {
      if (standardMode === 'custom') {
        const customStandards = await apiService.getCustomStandards(true);
        setCustomStandardsMap(customStandards.standardsMap || {});
      }
      const refreshed = await apiService.getModules(true, standardMode === 'custom' ? 'custom' : 'industry');
      if (refreshed && refreshed.length > 0) {
        setModulesData(refreshed);
      }
      setDataRefreshVersion((version) => version + 1);
    } catch (e) {
      console.warn('Using existing modules after pipeline run:', e);
    }
    setIsRefreshing(false);
    setToast({
      id: Date.now(),
      type: 'success',
      message: 'Orchestrator run completed. Dashboard data refreshed from Supabase.'
    });
  };

  const handlePipelineFailed = (message) => {
    setIsRefreshing(false);
    setToast({
      id: Date.now(),
      type: 'error',
      message: message || 'The orchestrator run failed. Check the run output for details.'
    });
  };

  return (
    <div className="app-container">
      {/* 1. Dark Top Header with YASH Logo & Success Factors Title */}
      <Navbar
        onGoHome={handleGoHome}
        onOpenConnectSystem={() => setIsModalOpen(true)}
        isConnected={isSystemConnected}
        backendStatus={backendStatus}
        onTriggerRefresh={handleTriggerRefreshPipeline}
        isRefreshing={isRefreshing}
        standardMode={standardMode}
        onSelectStandardMode={handleSelectStandardMode}
        onOpenUploadModal={() => setIsUploadModalOpen(true)}
        hasCustomStandards={hasCustomStandards}
      />

      {/* 2. Sub-Ribbon: Shown when inside a module (auto-hides in Deep Dive till hovered) */}
      {activeModule && (
        <div className={`module-ribbon-autohide-container ${isDeepDive ? 'is-autohide' : ''}`}>
          <ModuleRibbon
            modules={modulesData}
            activeModuleId={activeModuleId}
            onSelectModule={handleSelectModule}
            onGoHome={handleGoHome}
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
            refreshVersion={dataRefreshVersion}
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
        standards={standardMode === 'custom' ? 'custom' : 'industry'}
        onCompleted={handlePipelineCompleted}
        onFailed={handlePipelineFailed}
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

