import { useEffect, useState } from 'react';
import flagsmith from '@flagsmith/flagsmith';
import { FlagsmithProvider } from '@flagsmith/flagsmith/react';
import { CheckoutCard } from './components/CheckoutCard';

const ENV_KEY = import.meta.env.VITE_FLAGSMITH_ENVIRONMENT_KEY || '';

export default function App() {
  const [identity, setIdentity] = useState(() => `demo_visitor_${Math.floor(1000 + Math.random() * 9000)}`);
  const [ready, setReady] = useState(!ENV_KEY);

  useEffect(() => {
    if (!ENV_KEY) return;
    flagsmith
      .init({
        environmentID: ENV_KEY,
        identity,
        traits: { source: 'flagpilot_demo_app' },
      })
      .then(() => setReady(true))
      .catch(() => setReady(true));
  }, [identity]);

  const content = (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ maxWidth: 520, width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontSize: 12, letterSpacing: 1.2, textTransform: 'uppercase', color: '#38bdf8', fontWeight: 700 }}>
            CloudPulse Pro • Target App
          </span>
          <button
            onClick={() => setIdentity(`demo_visitor_${Math.floor(1000 + Math.random() * 9000)}`)}
            style={{
              background: '#1e293b',
              color: '#cbd5e1',
              border: '1px solid #334155',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            New Visitor ID ({identity.slice(-4)})
          </button>
        </div>
        {ready ? <CheckoutCard identity={identity} sdkConfigured={Boolean(ENV_KEY)} /> : <p>Loading Flagsmith...</p>}
      </div>
    </div>
  );

  if (!ENV_KEY) {
    return content;
  }

  return (
    <FlagsmithProvider flagsmith={flagsmith}>
      {content}
    </FlagsmithProvider>
  );
}
