// src/App.tsx
import { useState } from 'react';
import './index.css';
import { Launch } from './pages/Launch';
import { RunDashboard } from './pages/RunDashboard';

export default function App() {
  const [runId, setRunId] = useState<string | null>(null);

  return runId
    ? <RunDashboard runId={runId} onBack={() => setRunId(null)} />
    : <Launch onRunCreated={setRunId} />;
}
