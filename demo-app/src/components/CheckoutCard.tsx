import { useState } from 'react';
import flagsmith from '@flagsmith/flagsmith';

interface CheckoutCardProps {
  identity: string;
  sdkConfigured: boolean;
}

export function CheckoutCard({ identity, sdkConfigured }: CheckoutCardProps) {
  const activeFlagKey = 'checkout_experience';
  const activeEventName = 'checkout_completed';
  const defaultWinningVariant = 'control';

  const evaluated = sdkConfigured ? String(flagsmith.getValue(activeFlagKey) || defaultWinningVariant) : defaultWinningVariant;
  const isOneClick = evaluated === 'one_click' || evaluated === 'treatment';

  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [completed, setCompleted] = useState(false);

  const handleCheckout = () => {
    if (sdkConfigured) {
      flagsmith.trackEvent(activeEventName);
    }
    setCompleted(true);
  };

  return (
    <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: 28, boxShadow: '0 20px 50px rgba(0,0,0,0.45)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>Upgrade to CloudPulse Pro</h2>
        <span style={{ fontSize: 11, padding: '4px 10px', borderRadius: 999, background: isOneClick ? '#064e3b' : '#1e293b', color: isOneClick ? '#6ee7b7' : '#94a3b8', border: '1px solid rgba(255,255,255,0.1)' }}>
          Variant: {evaluated}
        </span>
      </div>

      <p style={{ color: '#94a3b8', fontSize: 14, lineHeight: 1.5, marginTop: 0 }}>
        Unlock unlimited team observability, Bayesian alerting, and instant rollbacks for $29/mo.
      </p>

      {completed ? (
        <div style={{ background: '#052e16', border: '1px solid #166534', borderRadius: 12, padding: 16, color: '#bbf7d0' }}>
          <strong>Order confirmed for {identity}!</strong>
          <div style={{ fontSize: 13, marginTop: 6 }}>
            Tracked conversion event: <code>{activeEventName}</code>
          </div>
          <button
            onClick={() => setCompleted(false)}
            style={{ marginTop: 12, background: '#16a34a', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontWeight: 600 }}
          >
            Reset Demo
          </button>
        </div>
      ) : isOneClick ? (
        <div>
          <p style={{ fontSize: 13, color: '#cbd5e1', marginBottom: 14 }}>
            Express Checkout enabled — your workspace billing profile is pre-verified.
          </p>
          <button
            onClick={handleCheckout}
            style={{ width: '100%', background: 'linear-gradient(135deg, #10b981, #06b6d4)', color: '#031510', border: 'none', borderRadius: 10, padding: '14px 18px', fontSize: 15, fontWeight: 700, cursor: 'pointer' }}
          >
            1-Click Instant Upgrade ($29/mo)
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input
            type="email"
            placeholder="Work email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ background: '#0f172a', border: '1px solid #334155', color: '#f8fafc', borderRadius: 8, padding: '10px 12px', fontSize: 14 }}
          />
          <input
            type="text"
            placeholder="Company name"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            style={{ background: '#0f172a', border: '1px solid #334155', color: '#f8fafc', borderRadius: 8, padding: '10px 12px', fontSize: 14 }}
          />
          <button
            onClick={handleCheckout}
            style={{ marginTop: 6, background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 10, padding: '12px 16px', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
          >
            Complete Standard Checkout
          </button>
        </div>
      )}
    </div>
  );
}
