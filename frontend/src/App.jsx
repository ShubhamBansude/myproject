// src/App.jsx

import React, { useState, useEffect, lazy, Suspense } from 'react';

// Lazy-load top-level routes for smaller initial bundle
const WelcomePage = lazy(() => import('./components/WelcomePage'));
const AuthGateway = lazy(() => import('./components/AuthGateway'));
const Dashboard = lazy(() => import('./components/Dashboard'));

function App() {
  // 'welcome' -> Landing Page
  // 'auth' -> Login/Signup Screen
  // 'dashboard' -> Logged-in Main App
  const [view, setView] = useState('welcome'); 
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [currentUser, setCurrentUser] = useState(null); // Stores user data {id, username, points}

  // Effect to restore session from storage on load
  useEffect(() => {
    try {
      const token = localStorage.getItem('authToken');
      const userRaw = localStorage.getItem('authUser');
      if (token && userRaw) {
        const user = JSON.parse(userRaw);
        setIsLoggedIn(true);
        setCurrentUser(user);
        setView('dashboard');
      }
    } catch {
      // Corrupt storage – clear and fallback to welcome
      localStorage.removeItem('authToken');
      localStorage.removeItem('authUser');
      setIsLoggedIn(false);
      setCurrentUser(null);
      setView('welcome');
    }
  }, []);

  // Preload likely-next route chunks during idle time
  useEffect(() => {
    const runIdle = (cb) => {
      if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
        // @ts-ignore - requestIdleCallback is not in TS lib by default
        window.requestIdleCallback(cb);
      } else {
        setTimeout(cb, 0);
      }
    };

    runIdle(() => {
      if (view === 'welcome') {
        import('./components/AuthGateway');
      } else if (view === 'auth') {
        import('./components/Dashboard');
      }
    });
  }, [view]);

  // Handler for successful login/signup
  const handleAuthSuccess = (userData, token) => {
    localStorage.setItem('authToken', token);
    try { localStorage.setItem('authUser', JSON.stringify(userData)); } catch { /* ignore */ }
    setIsLoggedIn(true);
    setCurrentUser(userData);
    setView('dashboard');
  };

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser');
    setIsLoggedIn(false);
    setCurrentUser(null);
    setView('welcome');
  };

  // Keep stored user in sync with in-memory changes
  useEffect(() => {
    if (!isLoggedIn) return;
    try {
      if (currentUser) localStorage.setItem('authUser', JSON.stringify(currentUser));
    } catch { /* ignore */ }
  }, [isLoggedIn, currentUser]);

  let content;
  
  if (view === 'welcome') {
    // 1. Landing Page
    content = <WelcomePage onGetStarted={() => setView('auth')} />;
  } else if (view === 'auth' && !isLoggedIn) {
    // 2. Auth Gateway
    content = <AuthGateway onAuthSuccess={handleAuthSuccess} />;
  } else if (isLoggedIn) {
    // 3. Main Dashboard
    content = <Dashboard currentUser={currentUser} onLogout={handleLogout} setCurrentUser={setCurrentUser} />;
  } else {
      // Fallback to welcome if logic fails
      content = <WelcomePage onGetStarted={() => setView('auth')} />;
  }
  
  return (
     <div className="min-h-screen w-screen bg-gray-50 font-sans antialiased">
      <Suspense fallback={<div className="p-6 text-gray-500">Loading…</div>}>
        {content}
      </Suspense>
    </div>
  );
}

export default App;





