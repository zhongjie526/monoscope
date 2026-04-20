import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
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
          <span className="logo">🐕</span>
          <div>
            <h1>Monad Watchdog</h1>
            <span>Fraud Detection & Analytics</span>
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
          {isOnline ? 'Neo4j Connected' : 'Neo4j Offline'}
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
