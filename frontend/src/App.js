import "App.css"; // fixed from '@/App.css'
import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { Toaster } from './components/ui/sonner';
import axios from 'axios';

// Pages
import Landing from './pages/Landing';
import AuthCallback from './pages/AuthCallback';
import Paywall from './pages/Paywall';
import Onboarding from './pages/Onboarding';
import Dashboard from './pages/Dashboard';
import Income from './pages/Income';
import Deals from './pages/Deals';
import Analytics from './pages/Analytics';
import Invoices from './pages/Invoices';
import Settings from './pages/Settings';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Protected Route Component with Paywall & Onboarding
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [accessStatus, setAccessStatus] = useState(null);
  const [checkingAccess, setCheckingAccess] = useState(true);

  useEffect(() => {
    const checkAccess = async () => {
      if (!user) {
        setCheckingAccess(false);
        return;
      }
      
      try {
        const response = await axios.get(`${API}/auth/access-status`, { withCredentials: true });
        setAccessStatus(response.data);
      } catch (error) {
        console.error('Error checking access:', error);
        setAccessStatus({ early_access: true, onboarding_complete: true });
      } finally {
        setCheckingAccess(false);
      }
    };

    if (!loading) {
      checkAccess();
    }
  }, [user, loading]);

  if (location.state?.user && !accessStatus) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (loading || checkingAccess) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/" replace />;
  }

  if (accessStatus && !accessStatus.early_access) {
    return <Paywall onAccessGranted={() => setAccessStatus({ ...accessStatus, early_access: true })} />;
  }

  if (accessStatus && !accessStatus.onboarding_complete) {
    return <Onboarding user={user} onComplete={() => setAccessStatus({ ...accessStatus, onboarding_complete: true })} />;
  }

  return children;
};

// App Router - handles session_id detection synchronously
const AppRouter = () => {
  const location = useLocation();

  if (location.hash?.includes('session_id=')) {
    return <AuthCallback />;
  }

  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/income"
        element={
          <ProtectedRoute>
            <Income />
          </ProtectedRoute>
        }
      />
      <Route
        path="/deals"
        element={
          <ProtectedRoute>
            <Deals />
          </ProtectedRoute>
        }
      />
      <Route
        path="/analytics"
        element={
          <ProtectedRoute>
            <Analytics />
          </ProtectedRoute>
        }
      />
      <Route
        path="/invoices"
        element={
          <ProtectedRoute>
            <Invoices />
          </ProtectedRoute>
        }
      />
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <AppRouter />
          <Toaster position="top-right" richColors />
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
