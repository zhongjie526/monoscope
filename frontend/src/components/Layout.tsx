import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Star,
  Shield,
  GitGraph,
  Activity,
} from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { getHealth } from '../services/api';

export default function Layout() {
  const { data: health } = useApi(() => getHealth(), []);
  const isOnline = health?.neo4j ?? false;

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <img src="/logo.svg" alt="Monoscope" className="logo" style={{ width: 32, height: 32 }} />
          <div>
            <h1 style={{ fontFamily: 'Outfit, sans-serif', textTransform: 'uppercase', letterSpacing: '2px', fontSize: 15, fontWeight: 600 }}>Monoscope</h1>
            <span style={{ fontFamily: 'Outfit, sans-serif', letterSpacing: '1px', textTransform: 'uppercase', fontSize: 9 }}>On-chain Intelligence</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
            <LayoutDashboard size={18} />
            Overview
          </NavLink>
          <NavLink to="/wallet" className={({ isActive }) => isActive ? 'active' : ''}>
            <Search size={18} />
            Wallet Lookup
          </NavLink>
          <NavLink to="/favourites" className={({ isActive }) => isActive ? 'active' : ''}>
            <Star size={18} />
            Favourites
          </NavLink>
          <NavLink to="/fraud" className={({ isActive }) => isActive ? 'active' : ''}>
            <Shield size={18} />
            Fraud Alerts
          </NavLink>
          <NavLink to="/graph" className={({ isActive }) => isActive ? 'active' : ''}>
            <GitGraph size={18} />
            Graph Explorer
          </NavLink>
          <NavLink to="/search" className={({ isActive }) => isActive ? 'active' : ''}>
            <Activity size={18} />
            AI Search
          </NavLink>
        </nav>

        <div className="sidebar-status">
          <span className={`status-dot ${isOnline ? '' : 'offline'}`} />
          {isOnline ? 'Connected' : 'Offline'}
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
