import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import WalletLookup from './pages/WalletLookup';
import FraudAlerts from './pages/FraudAlerts';
import GraphExplorer from './pages/GraphExplorer';
import AISearch from './pages/AISearch';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/wallet" element={<WalletLookup />} />
          <Route path="/wallet/:address" element={<WalletLookup />} />
          <Route path="/fraud" element={<FraudAlerts />} />
          <Route path="/graph" element={<GraphExplorer />} />
          <Route path="/search" element={<AISearch />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
